"""Durable-audit lifecycle for the Gateway surface.

Owns the full two-phase durable-audit lifecycle so the legacy
``routers/proxy.py`` file never grows Gateway behavior:

    open_durable_row()     insert_accepted + start whole-request renewal
    close_durable_row()    cancel renewal task (idempotent)
    finalize_durable_row() supervised finalize (bounded shield + strong ref)

Callers see a small dataclass with either a ``fail_response`` to return
immediately (durable write failed and the operator is configured
fail-closed) or a ``row_id`` + ``renewal_task`` pair to thread through
the request lifetime.

Hard-kill loss is caught by the Phase 4 reconciler; the supervised
task pattern here reduces the loss window to "process killed within a
few hundred ms of stream end."
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import settings
from app.guard.audit import finalize, insert_accepted, renew_lease
from app.guard.router import fail_closed as _fail_closed


log = structlog.get_logger(__name__)


# Module-level strong-ref set so an in-flight finalize task cannot be
# GC'd by the loop before it completes. One set per worker process.
_PENDING_FINALIZES: set[asyncio.Task] = set()


@dataclass
class DurableRow:
    """Handle threaded through the request lifecycle.

    Exactly one of ``row_id`` or ``fail_response`` will be set — never
    both, never neither when the caller enters the durable path.
    """
    row_id: str | None = None
    renewal_task: asyncio.Task | None = None
    fail_response: Any = None


# ─── Open ─────────────────────────────────────────────────────────────


async def open_durable_row(
    *,
    workspace_id: str,
    clerk_user_id: str | None,
    ai_tool: str,
    provider: str,
    model: str,
    body: dict,
    prompt_summary: str,
    user_email: str | None,
    agent_identity_id: str | None,
    route: str,
    hook_session_id: str | None,
    routing_meta: dict | None,
    conductai_run_id: str | None,
    conductai_workflow: str | None,
    conductai_workflow_id: str | None,
    request_correlation_id: str | None,
) -> DurableRow:
    """Insert the accepted row and start whole-request lease renewal.

    Returns a ``DurableRow`` with ``row_id`` + optional ``renewal_task``
    on success, or ``fail_response`` set on real write failure (503) /
    UUID4 collision (409).
    """
    from sqlalchemy.exc import IntegrityError

    # #1995 canary — deterministic per-workspace gate. Global flag is
    # still the kill switch; allowlist + pct control incremental rollout
    # without a code deploy. Same workspace always lands in the same
    # bucket, so a workspace never oscillates between the two writer
    # paths mid-session.
    if not settings.durable_audit_enabled_for(workspace_id):
        return DurableRow()

    # Server-owned request_id. Client X-Request-Id lives in routing_meta.
    # client_request_id as correlation metadata only — never a
    # uniqueness key because a client-supplied value cannot be trusted
    # for cross-tenant safety.
    request_id = str(uuid.uuid4())
    if request_correlation_id and isinstance(routing_meta, dict):
        routing_meta = {**routing_meta, "client_request_id": request_correlation_id}
    elif request_correlation_id:
        routing_meta = {"client_request_id": request_correlation_id}

    try:
        row_id = insert_accepted(
            workspace_id, clerk_user_id, ai_tool, provider, model,
            request_id=request_id,
            body=body,
            prompt_summary=prompt_summary,
            user_email=user_email,
            agent_identity_id=agent_identity_id,
            route=route,
            hook_session_id=hook_session_id,
            routing_meta=routing_meta,
            conductai_run_id=conductai_run_id,
            conductai_workflow=conductai_workflow,
            conductai_workflow_id=conductai_workflow_id,
        )
    except IntegrityError:
        # Server-generated UUID4 collision is astronomically unlikely
        # (2^-122). Return generic 409 with no receipt or state.
        log.warning(
            "guard.gateway.internal_request_id_collision",
            request_id=request_id,
        )
        return DurableRow(fail_response=_fail_closed(
            409,
            "Duplicate durable-audit request id. Retry the request.",
        ))
    except Exception as e:
        if settings.guard_durable_audit_fail_closed:
            log.error(
                "guard.gateway.durable_audit_fail_closed",
                err=str(e),
                request_id=request_id,
            )
            return DurableRow(fail_response=_fail_closed(
                503,
                "Guard durable audit write failed — refusing to forward "
                "inference without a durable record. Retry the request.",
            ))
        log.warning(
            "guard.gateway.durable_audit_fail_open",
            err=str(e),
            request_id=request_id,
        )
        return DurableRow()

    # Whole-request renewal: covers the header-wait window on non-
    # streaming plus the initial-connect window on streaming.
    renew_interval = settings.guard_durable_audit_stream_renew_seconds
    renewal_task: asyncio.Task | None = None
    if renew_interval > 0:
        lease_seconds = settings.guard_durable_audit_lease_seconds
        renewal_task = asyncio.create_task(
            _renewal_loop(row_id, workspace_id, renew_interval, lease_seconds)
        )

    return DurableRow(row_id=row_id, renewal_task=renewal_task)


# ─── Close ────────────────────────────────────────────────────────────


async def close_durable_row(durable: DurableRow) -> None:
    """Cancel the whole-request renewal task. Idempotent."""
    if durable.renewal_task is None or durable.renewal_task.done():
        return
    durable.renewal_task.cancel()
    try:
        await durable.renewal_task
    except BaseException:
        pass


# ─── Finalize ─────────────────────────────────────────────────────────


async def finalize_durable_row(
    *,
    row_id: str,
    workspace_id: str,
    decision: str,
    provider: str,
    model: str,
    body: dict,
    response_bytes: bytes | None,
    duration_ms: int,
    rule_id: str | None,
    routing_meta: dict | None,
    execution_status: str | None,
    result_summary: str | None,
    clerk_user_id: str | None,
    ai_tool: str,
    user_email: str | None,
    bounded_timeout: float = 5.0,
) -> None:
    """Supervised finalize with bounded shield.

    Runs the sync ``finalize()`` SQL in a thread so the event loop is
    not blocked, wraps it in a shielded task with a strong module-level
    reference so it survives caller cancellation, and waits up to
    ``bounded_timeout`` for completion. On timeout the task keeps
    running under supervision; on caller cancellation the task keeps
    running and the caller sees the cancel.

    Phase 4 reconciler catches any tail that a hard-kill drops.
    """
    task = asyncio.create_task(
        asyncio.to_thread(
            finalize,
            row_id, workspace_id,
            decision=decision,
            provider=provider,
            model=model,
            body=body,
            response_bytes=response_bytes,
            duration_ms=duration_ms,
            rule_id=rule_id,
            routing_meta=routing_meta,
            execution_status=execution_status,
            result_summary=result_summary,
            clerk_user_id=clerk_user_id,
            ai_tool=ai_tool,
            user_email=user_email,
        )
    )
    _register_finalize_task(task, label=f"finalize:{row_id}")

    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=bounded_timeout)
    except asyncio.TimeoutError:
        log.info(
            "guard.gateway.finalize_bounded_wait_timeout",
            row_id=row_id,
            timeout=bounded_timeout,
        )
    except asyncio.CancelledError:
        log.info(
            "guard.gateway.finalize_bounded_wait_cancelled",
            row_id=row_id,
        )
        raise


def _register_finalize_task(task: asyncio.Task, *, label: str) -> None:
    _PENDING_FINALIZES.add(task)
    def _observe(t: asyncio.Task) -> None:
        _PENDING_FINALIZES.discard(t)
        if t.cancelled():
            log.warning("guard.gateway.finalize_cancelled", label=label)
            return
        exc = t.exception()
        if exc is not None:
            log.error("guard.gateway.finalize_failed", label=label, err=str(exc))
    task.add_done_callback(_observe)


# ─── Test hooks ───────────────────────────────────────────────────────


def pending_finalize_count() -> int:
    return len(_PENDING_FINALIZES)


async def drain_pending_finalizes(timeout: float = 5.0) -> int:
    if not _PENDING_FINALIZES:
        return 0
    pending = list(_PENDING_FINALIZES)
    done, still = await asyncio.wait(pending, timeout=timeout)
    return len(still)


# ─── Private helpers ──────────────────────────────────────────────────


async def _renewal_loop(
    row_id: str,
    workspace_id: str,
    renew_interval: int,
    lease_seconds: int,
) -> None:
    while True:
        try:
            await asyncio.sleep(renew_interval)
        except asyncio.CancelledError:
            return
        try:
            await asyncio.to_thread(
                renew_lease,
                row_id, workspace_id,
                additional_seconds=lease_seconds,
            )
        except Exception:
            log.warning("guard.gateway.whole_request_renewal_swallowed")
