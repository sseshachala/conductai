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

PR 2.5: for ``NativeHTTPTransport`` streaming attempts, the transport
raises ``httpx.HTTPStatusError`` on 4xx/5xx *before* returning any
bytes (see ``_execute_stream``). That means the coordinator's normal
retry classifier walks pre-body upstream errors, but the moment the
transport returns a ``StreamingUpstream`` (or LiteLLM stream generator)
the coordinator records success and returns — no chance to retry
against a fallback target once headers went out.

Retries live here. LiteLLM's own retry ladder is off (``num_retries=0``
inside ``LiteLLMTransport``), and the passthrough transports don't
retry either. This is the single owner.

Nothing in this module reads the database. The caller passes a
``ResolvedV2`` (from ``resolve_v2()``), a ``CredentialResolver``, and
the client payload. That keeps the coordinator unit-testable without
Postgres + Vault decryption plumbing.

The gateway route wiring (reads ``model:`` from body, calls
``resolve_v2``, then calls into this module) lives in
``gateway_handler.py`` — separate concern, kept out of the
coordinator so this module stays unit-testable without FastAPI.

Transports the coordinator dispatches to:

- ``NativeHTTPTransport`` (``transport=native_http``) — direct HTTP
  to Anthropic + OpenAI. Streaming supported.
- ``LiteLLMTransport`` (``transport=litellm_sdk``) — LiteLLM SDK for
  translation cases. Non-streaming path is production; streaming
  through the SDK is a follow-up.
- ``HTTPPassthroughTransport`` (``transport=http_passthrough``) —
  external gateways. OpenRouter is the reference integration; other
  integrations (Portkey / Helicone / Azure / Custom) fail at the
  transport layer with ``UnsupportedPassthroughIntegration`` until
  each ships its per-integration auth-header semantics.
"""
from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Callable
from uuid import UUID

import structlog

from app.modules.guard.gateway_config import (
    HTTPPassthroughTarget,
    LiteLLMSDKTarget,
    NativeHTTPTarget,
    Operation,
)
from app.modules.guard.gateway_runtime import ResolvedV2
from app.runtime.http_passthrough_transport import HTTPPassthroughTransport
from app.runtime.litellm_transport import CredentialResolver, LiteLLMTransport
from app.runtime.native_http_transport import NativeHTTPTransport


log = structlog.get_logger(__name__)


class UnsupportedTransport(Exception):
    """Raised when the coordinator encounters a target type it can't
    dispatch. Should be unreachable in practice — the schema union
    covers every legal target and each has a matching transport wired
    in ``_dispatch``. Kept as a defensive fallback for a corrupted
    profile row (e.g. a schema migration mid-request) rather than a
    silent request-time crash.
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
class PolicyBlock:
    """A per-target policy re-evaluation result meaning "do not dispatch
    this target". Coordinator treats it like a permanent per-target
    error — records the attempt with error_class='PolicyBlock' and tries
    the next target. If every target is blocked, the coordinator raises
    ``AllAttemptsFailed`` and the caller renders 451.

    Carries the gate's ``rule_id`` + ``message`` so the audit row (and
    the client's 451 envelope, if that's the outcome) can identify the
    rule that fired instead of a bare "everything blocked".
    """
    rule_id: str
    message: str
    matched_rules: list[str] | None = None


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
        native_http_transport: NativeHTTPTransport | None = None,
        http_passthrough_transport: HTTPPassthroughTransport | None = None,
    ) -> None:
        self._sdk = sdk_transport or LiteLLMTransport()
        self._native = native_http_transport or NativeHTTPTransport()
        self._passthrough = (
            http_passthrough_transport or HTTPPassthroughTransport()
        )

    async def execute(
        self,
        *,
        resolved: ResolvedV2,
        operation: Operation,
        payload: dict[str, Any],
        credential_resolver: CredentialResolver,
        stream: bool = False,
        policy_check: Callable[[Any], "PolicyBlock | None"] | None = None,
        client_headers: dict[str, str] | None = None,
        vendor_credential_resolver: CredentialResolver | None = None,
    ) -> CoordinatorResult:
        """Walk targets in priority order, honouring max_attempts and
        timeout_seconds. Returns the first successful response.

        Publish-time capability catalog already verified that every
        target advertises the requested operation, so runtime failure
        modes here are transport/network/upstream — not schema.

        X1 — per-target policy re-eval. ``policy_check`` is called with
        each target right before dispatch. If it returns a
        ``PolicyBlock``, the target is skipped (recorded as
        ``error_class='PolicyBlock'``), the coordinator tries the next
        target. If every target is blocked, ``AllAttemptsFailed`` fires
        and the handler renders 451 naming the last block's rule.

        Rationale: the ingress policy evaluation runs against the
        cond-* alias, which resolves to a *set* of possible target
        models. A rule keyed on the real target model (``gpt-4o``,
        ``claude-sonnet``) MUST be re-evaluated once we know which
        target we're about to hit — otherwise the alias is a
        model-policy bypass.
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

            # X1 per-target policy re-eval BEFORE dispatch — no wire hit
            # if this target is blocked by policy against its model.
            if policy_check is not None:
                # Support both sync and async policy_check callbacks. Async
                # is preferred so the callback can offload its sync DB
                # work via run_in_threadpool without stalling the event
                # loop under high concurrency.
                # PR review fix: bound the awaitable policy check by the
                # coordinator's remaining budget so a slow eval cannot
                # consume the whole deadline and then trigger a paid
                # upstream call after expiry.
                _pc_result = policy_check(target)
                if inspect.isawaitable(_pc_result):
                    try:
                        block = await asyncio.wait_for(_pc_result, timeout=remaining)
                    except asyncio.TimeoutError:
                        # Policy eval blew the request budget. Record the
                        # target as a deadline attempt and stop — no
                        # further targets get charged an upstream call.
                        attempts.append(_deadline_record(target, time.monotonic()))
                        break
                else:
                    block = _pc_result
                # Recompute remaining after the (possibly slow) policy check;
                # if the budget is gone, refuse dispatch on this target.
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    attempts.append(_deadline_record(target, time.monotonic()))
                    break
                if block is not None:
                    attempt_start = time.monotonic()
                    attempts.append(AttemptRecord(
                        target_id=target.id,
                        transport=target.transport,
                        provider_or_integration=_name_of(target),
                        started_at_monotonic=attempt_start,
                        completed_at_monotonic=attempt_start,
                        succeeded=False,
                        error_class="PolicyBlock",
                        error_summary=(
                            f"rule_id={block.rule_id}: {block.message}"
                        )[:200],
                    ))
                    log.info(
                        "gateway.v2.attempt_policy_block",
                        target_id=target.id,
                        rule_id=block.rule_id,
                        revision_id=str(resolved.revision_id),
                    )
                    continue

            attempt_start = time.monotonic()
            try:
                response = await asyncio.wait_for(
                    self._dispatch(
                        target=target,
                        operation=operation,
                        payload=payload,
                        credential_resolver=credential_resolver,
                        stream=stream,
                        client_headers=client_headers,
                        vendor_credential_resolver=vendor_credential_resolver,
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
                # #2001 review fix — retry classification. Fall through
                # to the next target ONLY on transient failure classes
                # (network drop, upstream 5xx, DNS, socket, LiteLLM's
                # own APIError family). Auth failures, validation
                # errors, credential-resolution errors are permanent
                # for this request — trying the next target won't help
                # and burns budget the request can't spare.
                if not _is_retryable(exc):
                    log.info(
                        "gateway.v2.attempt_permanent",
                        target_id=target.id,
                        error_class=type(exc).__name__,
                        revision_id=str(resolved.revision_id),
                    )
                    raise AllAttemptsFailed(attempts) from exc
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
        client_headers: dict[str, str] | None = None,
        vendor_credential_resolver: CredentialResolver | None = None,
    ) -> Any:
        if isinstance(target, NativeHTTPTarget):
            return await self._native.execute(
                target=target,
                operation=operation,
                payload=payload,
                credential_resolver=credential_resolver,
                stream=stream,
                client_headers=client_headers,
            )
        if isinstance(target, LiteLLMSDKTarget):
            # LiteLLM transport doesn't take client_headers yet — LiteLLM's
            # own SDK has an ``extra_headers`` kwarg but the mapping is
            # provider-specific and non-trivial for the ``anthropic-beta``
            # class of headers. Left for a follow-up; native_http covers
            # the launch path where vendor headers matter most.
            return await self._sdk.execute(
                target=target,
                operation=operation,
                payload=payload,
                credential_resolver=credential_resolver,
                stream=stream,
            )
        if isinstance(target, HTTPPassthroughTarget):
            return await self._passthrough.execute(
                target=target,
                operation=operation,
                payload=payload,
                credential_resolver=credential_resolver,
                stream=stream,
                client_headers=client_headers,
                vendor_credential_resolver=vendor_credential_resolver,
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


# Exception class names known to be PERMANENT failures — do not retry.
# Checked BEFORE the transient set because the OpenAI/Anthropic SDK
# inheritance graph puts ``AuthenticationError`` → ``APIStatusError`` →
# ``APIError``, so a plain MRO walk over the transient set would
# misclassify an auth failure as retryable.
_PERMANENT_ERROR_CLASSES: frozenset[str] = frozenset({
    # OpenAI/Anthropic/LiteLLM 4xx client-error classes
    "AuthenticationError",       # 401
    "PermissionDeniedError",     # 403
    "NotFoundError",             # 404
    "BadRequestError",           # 400
    "UnprocessableEntityError",  # 422
    "ConflictError",             # 409
    "InvalidRequestError",       # LiteLLM
    "ContextWindowExceededError",
    "ContentPolicyViolationError",
    "BudgetExceededError",
    # Our own client-error family — payload validation, schema issues,
    # dev-time bugs. Retrying against the next target would fail the
    # exact same way.
    "ValueError",
    "TypeError",
    "KeyError",
    "UnsupportedPayloadFields",
})


# HTTP status codes that are ALWAYS permanent when the SDK exposes one
# on the exception (client errors that will fail identically on the
# next target). 408 (Request Timeout) and 429 (Too Many Requests)
# deliberately excluded — those are transient.
_PERMANENT_STATUS_CODES: frozenset[int] = frozenset({
    400, 401, 402, 403, 404, 405, 406, 409, 410, 411, 412, 413, 414,
    415, 416, 417, 418, 421, 422, 423, 424, 426, 428, 431, 451,
})


# Exception class names that count as transient upstream failures worth
# a fallback attempt.
#
# Class NAMES are compared instead of importing LiteLLM's exception
# tree so the transport module and its dependencies stay decoupled from
# the LiteLLM install for unit tests.
_TRANSIENT_ERROR_CLASSES: frozenset[str] = frozenset({
    # LiteLLM's own transient family
    "APIConnectionError",
    "APIError",
    "InternalServerError",
    "ServiceUnavailableError",
    "Timeout",
    "RateLimitError",
    # stdlib / httpx / anyio commons
    "TimeoutError",
    "ConnectionError",
    "ConnectionRefusedError",
    "ConnectionResetError",
    "ConnectionAbortedError",
    "ReadTimeout",
    "ConnectTimeout",
    "PoolTimeout",
    "RemoteProtocolError",
    "NetworkError",
})


def _is_retryable(exc: BaseException) -> bool:
    """Return True only for transient upstream failures worth trying
    the next target for.

    Order matters:
      1. Permanent class names (auth, bad request, our ValueError) →
         never retry, even if a parent class is in the transient set.
      2. HTTP status on the exception → 4xx permanent (except 408/429),
         5xx transient.
      3. Transient class names via MRO walk → retry.
      4. Default → not retryable (fail-safe).
    """
    mro_names = {cls.__name__ for cls in type(exc).__mro__}
    if mro_names & _PERMANENT_ERROR_CLASSES:
        return False

    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        if response is not None:
            status = getattr(response, "status_code", None)
    if isinstance(status, int):
        if status in _PERMANENT_STATUS_CODES:
            return False
        if status == 408 or status == 429 or status >= 500:
            return True

    return bool(mro_names & _TRANSIENT_ERROR_CLASSES)


__all__ = [
    "AllAttemptsFailed",
    "AttemptCoordinator",
    "AttemptRecord",
    "CoordinatorResult",
    "PolicyBlock",
    "UnsupportedTransport",
]
