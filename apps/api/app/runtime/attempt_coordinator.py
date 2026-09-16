"""Attempt coordinator for the v2 request path (#2001 review fix).

The v2 profile advertises an ordered ``targets`` list plus
``max_attempts`` and ``timeout_seconds``. This module executes that
contract: it walks targets in order, obeys the attempt cap and the
end-to-end deadline, resolves per-attempt credentials via a caller-
supplied resolver, and returns the first successful response.

Streaming invariant: once the underlying transport starts emitting
bytes (``stream=True``), no further attempts fire. The caller is
responsible for passing ``stream`` correctly per operation; this
coordinator only enforces the "no attempt N+1 after first byte"
invariant by delegating streaming responses back to the caller as-is
without wrapping them in retry logic.

Retries live here. LiteLLM's own retry ladder is off (``num_retries=0``
inside ``LiteLLMTransport``), and the passthrough transports don't
retry either. This is the single owner.

Nothing in this module reads the database. The caller passes a
``ResolvedV2`` (from ``resolve_v2()``), a ``CredentialResolver``, and
the client payload. That keeps the coordinator unit-testable without
Postgres + Vault decryption plumbing.

Not shipped in this file:

- The gateway route wiring (reads ``model:`` from body, calls
  ``resolve_v2``, then calls into this module). That's a request-path
  change in ``gateway_handler.py`` — separate concern, worth its own
  review.
- HTTP passthrough execution. The v2 launch supports the LiteLLM SDK
  transport only; passthrough targets in a published profile raise
  ``UnsupportedTransport`` here until commit N+1 of the wiring PR
  lands the ``HTTPPassthroughExecutor``.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from app.modules.guard.gateway_config import (
    HTTPPassthroughTarget,
    LiteLLMSDKTarget,
    Operation,
)
from app.modules.guard.gateway_runtime import ResolvedV2
from app.runtime.litellm_transport import CredentialResolver, LiteLLMTransport


log = structlog.get_logger(__name__)


class UnsupportedTransport(Exception):
    """Raised when the coordinator encounters a target it can't execute.

    Current launch set is ``transport=litellm_sdk`` only. HTTP passthrough
    targets are legal in the schema (and can be published — the capability
    catalog gates certified integrations), but the executor for them
    lands in a follow-up. Publishing a passthrough target and then
    letting a request find it here is a bug we surface loudly rather
    than falling back to the legacy proxy path.
    """


class AllAttemptsFailed(Exception):
    """No target in the ordered list produced a successful response
    inside the profile's ``max_attempts`` and ``timeout_seconds``.

    The caller's ``routing_meta`` will already contain each attempt's
    error; this exception is the signal to the request handler that
    it must return a fail-closed response to the client.
    """

    def __init__(self, attempts: list["AttemptRecord"]):
        self.attempts = attempts
        summary = "; ".join(
            f"{a.target_id}={a.error_class}" for a in attempts
        )
        super().__init__(f"all attempts failed: {summary}")


@dataclass(frozen=True)
class AttemptRecord:
    """One attempt's outcome — pinned in routing_meta for the audit row.

    Callers write these into the durable audit row so the Flight
    Recorder can show which target served the request, how many
    fell through, and what each one failed on.
    """
    target_id: str
    transport: str
    provider_or_integration: str
    started_at_monotonic: float
    completed_at_monotonic: float
    succeeded: bool
    error_class: str | None
    error_summary: str | None


@dataclass(frozen=True)
class CoordinatorResult:
    """Success payload — the response to hand back to the client + the
    audit attributes to pin in routing_meta.

    The revision_id + attempts list are what the durable-audit
    lifecycle writes into the row so publish → attempt → response is
    reconstructable end-to-end.
    """
    response: Any
    revision_id: UUID
    attempts: list[AttemptRecord]
    winning_target_id: str


class AttemptCoordinator:
    """Owns the v2 attempt loop.

    One instance per worker process. State per request lives entirely
    on the ``execute()`` call frame.
    """

    def __init__(
        self,
        *,
        sdk_transport: LiteLLMTransport | None = None,
    ) -> None:
        self._sdk = sdk_transport or LiteLLMTransport()

    async def execute(
        self,
        *,
        resolved: ResolvedV2,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver: CredentialResolver,
        stream: bool = False,
    ) -> CoordinatorResult:
        """Walk targets in priority order, honouring max_attempts and
        timeout_seconds. Returns the first successful response.

        Publish-time capability catalog already verified that every
        target advertises the requested operation, so runtime failure
        modes here are transport/network/upstream — not schema.
        """
        profile = resolved.profile
        if operation not in profile.accepts:
            raise ValueError(
                f"profile does not accept operation {operation!r}; "
                f"advertises {list(profile.accepts)!r}"
            )

        started = time.monotonic()
        deadline = started + profile.timeout_seconds
        attempts: list[AttemptRecord] = []
        cap = min(profile.max_attempts, len(profile.targets))

        for target in profile.targets[:cap]:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                attempts.append(_deadline_record(target, time.monotonic()))
                break

            attempt_start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self._dispatch(
                        target=target,
                        operation=operation,
                        payload=payload,
                        credential_resolver=credential_resolver,
                        stream=stream,
                    ),
                    timeout=remaining,
                )
            except asyncio.TimeoutError as exc:
                attempts.append(AttemptRecord(
                    target_id=target.id,
                    transport=target.transport,
                    provider_or_integration=_name_of(target),
                    started_at_monotonic=attempt_start,
                    completed_at_monotonic=time.monotonic(),
                    succeeded=False,
                    error_class="TimeoutError",
                    error_summary=str(exc)[:200] or "attempt timed out",
                ))
                log.info(
                    "gateway.v2.attempt_timeout",
                    target_id=target.id, revision_id=str(resolved.revision_id),
                )
                continue
            except UnsupportedTransport:
                # Publishing a passthrough target while its executor
                # doesn't exist is a config error, not a transient
                # failure — raise so the request handler surfaces
                # "profile publish gated a target we can't execute" to
                # the operator rather than silently trying every target
                # in sequence and giving the client a misleading 5xx.
                raise
            except Exception as exc:  # noqa: BLE001
                attempts.append(AttemptRecord(
                    target_id=target.id,
                    transport=target.transport,
                    provider_or_integration=_name_of(target),
                    started_at_monotonic=attempt_start,
                    completed_at_monotonic=time.monotonic(),
                    succeeded=False,
                    error_class=type(exc).__name__,
                    error_summary=str(exc)[:200],
                ))
                log.info(
                    "gateway.v2.attempt_failed",
                    target_id=target.id, error_class=type(exc).__name__,
                    revision_id=str(resolved.revision_id),
                )
                continue

            attempts.append(AttemptRecord(
                target_id=target.id,
                transport=target.transport,
                provider_or_integration=_name_of(target),
                started_at_monotonic=attempt_start,
                completed_at_monotonic=time.monotonic(),
                succeeded=True,
                error_class=None,
                error_summary=None,
            ))
            return CoordinatorResult(
                response=response,
                revision_id=resolved.revision_id,
                attempts=attempts,
                winning_target_id=target.id,
            )

        raise AllAttemptsFailed(attempts)

    async def _dispatch(
        self,
        *,
        target,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver: CredentialResolver,
        stream: bool,
    ) -> Any:
        if isinstance(target, LiteLLMSDKTarget):
            return await self._sdk.execute(
                target=target,
                operation=operation,
                payload=payload,
                credential_resolver=credential_resolver,
                stream=stream,
            )
        if isinstance(target, HTTPPassthroughTarget):
            raise UnsupportedTransport(
                f"target {target.id!r} uses transport=http_passthrough "
                f"which the coordinator does not execute yet. Publish "
                f"gate should have rejected this configuration; report "
                f"the discrepancy to ops."
            )
        raise UnsupportedTransport(f"unknown target type: {type(target).__name__}")


def _deadline_record(target, now: float) -> AttemptRecord:
    return AttemptRecord(
        target_id=target.id,
        transport=target.transport,
        provider_or_integration=_name_of(target),
        started_at_monotonic=now,
        completed_at_monotonic=now,
        succeeded=False,
        error_class="DeadlineExceeded",
        error_summary="profile timeout_seconds exhausted before attempt could start",
    )


def _name_of(target) -> str:
    if isinstance(target, LiteLLMSDKTarget):
        return target.provider
    if isinstance(target, HTTPPassthroughTarget):
        return target.integration
    return "unknown"


__all__ = [
    "AllAttemptsFailed",
    "AttemptCoordinator",
    "AttemptRecord",
    "CoordinatorResult",
    "UnsupportedTransport",
]
