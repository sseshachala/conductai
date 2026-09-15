"""Durable-audit lifecycle for the Gateway surface.

Owns the two-phase durable audit lifecycle end-to-end so the legacy
``routers/proxy.py`` file never grows new Gateway behavior:

    open_durable_row()  →  insert_accepted + start whole-request renewal
    close_durable_row() →  cancel renewal task; observe outcome

Callers see a small dataclass with either a ``fail_response`` to return
immediately (durable write failed and the operator is configured
fail-closed) or a ``row_id`` + ``renewal_task`` pair to thread through
the request lifetime.

Finalization stays where the response body is materialised —
``_stream_chunks`` for streaming, ``_schedule_audit`` for non-streaming
— because those paths already know the exact bytes and duration.
The supervised task pattern (module-level strong ref + done-callback +
bounded wait_for/shield) lives in ``guard/router.py`` where the write
happens.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import structlog


log = structlog.get_logger(__name__)


@dataclass
class DurableRow:
    """Handle the caller threads through the request lifecycle.

    Exactly one of ``row_id`` or ``fail_response`` will be set — never
    both, never neither. This makes the caller's short-circuit
    unambiguous: ``if row.fail_response: return row.fail_response``.
    """

    row_id: str | None = None
    renewal_task: asyncio.Task | None = None
    fail_response: Any = None


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
    db,
) -> DurableRow:
    """Insert the accepted row and start whole-request lease renewal.

    Returns a DurableRow with either row_id + renewal_task populated
    (success) or fail_response set (fail-closed on real write failure,
    409 on internal-id collision).
    """
    from sqlalchemy.exc import IntegrityError

    from app.core.config import settings
    from app.guard.audit import insert_accepted, renew_lease

    if not settings.guard_use_durable_audit:
        # Legacy single-phase writer path — nothing for the lifecycle
        # to own. Caller falls through to the pre-durable behavior.
        return DurableRow()

    import uuid as _uuid

    # Server-owned request_id. Client X-Request-Id lives in
    # routing_meta.client_request_id as correlation metadata only —
    # never as a uniqueness key.
    request_id = str(_uuid.uuid4())
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
        # (2^-122). Return 409 with no receipt id or lifecycle state
        # so the caller cannot fingerprint another workspace's row.
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
        return DurableRow()  # single-phase fallback

    # Whole-request renewal: covers the header-wait window on
    # non-streaming plus the initial-connect window on streaming.
    # _stream_chunks will spawn its own renewal for the stream body.
    renew_interval = settings.guard_durable_audit_stream_renew_seconds
    renewal_task: asyncio.Task | None = None
    if renew_interval > 0:
        lease_seconds = settings.guard_durable_audit_lease_seconds
        renewal_task = asyncio.create_task(
            _whole_request_renewal_loop(
                row_id, workspace_id, renew_interval, lease_seconds
            )
        )

    return DurableRow(row_id=row_id, renewal_task=renewal_task)


async def close_durable_row(durable: DurableRow) -> None:
    """Cancel the whole-request renewal task. Idempotent."""
    if durable.renewal_task is None or durable.renewal_task.done():
        return
    durable.renewal_task.cancel()
    try:
        await durable.renewal_task
    except BaseException:
        # Renewal loop swallows its own exceptions; awaiting the
        # cancelled task raises CancelledError, which we ignore because
        # the caller is on the normal response path.
        pass


async def _whole_request_renewal_loop(
    row_id: str,
    workspace_id: str,
    renew_interval: int,
    lease_seconds: int,
) -> None:
    from app.guard.audit import renew_lease
    while True:
        try:
            await asyncio.sleep(renew_interval)
        except asyncio.CancelledError:
            return
        try:
            await asyncio.to_thread(
                renew_lease,
                row_id,
                workspace_id,
                additional_seconds=lease_seconds,
            )
        except Exception:
            log.warning("guard.gateway.whole_request_renewal_swallowed")


def _fail_closed(status: int, message: str, *, extra: dict | None = None):
    """Local import trampoline — avoids a circular import with proxy.py."""
    from app.guard.router import fail_closed
    return fail_closed(status, message, extra=extra)
