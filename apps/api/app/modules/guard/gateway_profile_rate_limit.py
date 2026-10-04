"""Atomic profile and agent-wide RPM and reserved/actual TPM admission."""
from __future__ import annotations

import base64
import json
import time
from dataclasses import dataclass
from uuid import UUID

import structlog
from app.models.gateway_profile import GatewayProfile, GatewayProfileRateLimit
from app.modules.guard.models import GuardRateLimit
from app.modules.guard.rate_limit import _redis_client
from app.runtime.accounting.contracts import UsageCompleteness
from app.runtime.accounting.normalizers import ProviderFamily, normalize_json, normalize_sse

log = structlog.get_logger(__name__)

# Check every bucket before incrementing any of them. Rejected requests cannot
# consume quota, and an agent cap cannot bypass the shared profile cap.
_ADMIT = """
for i, key in ipairs(KEYS) do
    local current = tonumber(redis.call('GET', key) or '0')
    local cap = tonumber(ARGV[2*i])
    local amount = tonumber(ARGV[2*i+1])
    if current + amount > cap then return {0, i, current} end
end
for i, key in ipairs(KEYS) do
    redis.call('INCRBY', key, ARGV[2*i+1])
    redis.call('EXPIRE', key, ARGV[1])
end
return {1}
"""
_SETTLE = """
for _, key in ipairs(KEYS) do
    if redis.call('EXISTS', key) == 1 then
        local value = math.max(0, tonumber(redis.call('GET', key)) + tonumber(ARGV[1]))
        redis.call('SET', key, value, 'KEEPTTL')
    end
end
return 1
"""


@dataclass
class ProfileRateAdmission:
    reserved_tokens: int
    token_keys: list[str]
    finished: bool = False


@dataclass
class ProfileRateDecision:
    limited: bool = False
    reason: str | None = None
    metric: str | None = None
    limit: int | None = None
    current: int | None = None
    scope: str = "profile"
    status: int = 429
    retry_after: int = 60
    admission: ProfileRateAdmission | None = None


def reserved_profile_tokens(body: dict, operation: str) -> int:
    from app.runtime.accounting.estimator import estimate_tokens
    estimate = estimate_tokens(body)
    return estimate.input_tokens + (0 if operation == "anthropic_count_tokens" else estimate.output_tokens_allowance)


def check_profile_rate_limit(db, *, workspace_id: str, profile_id: UUID | None,
                             revision_id: UUID, agent_identity_id: str | None,
                             reserved_tokens: int) -> ProfileRateDecision:
    retry_after = 60 - int(time.time()) % 60
    try:
        from app.core.workspace_context import set_workspace_rls
        set_workspace_rls(db, workspace_id)
        if profile_id is None:
            profile = db.query(GatewayProfile).filter(
                GatewayProfile.active_revision_id == revision_id,
                GatewayProfile.workspace_id == UUID(str(workspace_id)),
            ).first()
            if profile is None:
                raise ValueError("Profile unavailable")
            profile_id = profile.id
        rows = db.query(GatewayProfileRateLimit).filter(
            GatewayProfileRateLimit.workspace_id == UUID(str(workspace_id)),
            GatewayProfileRateLimit.profile_id == profile_id,
            GatewayProfileRateLimit.agent_identity_id.is_(None),
        ).all()
        agent_rows = db.query(GuardRateLimit).filter(
            GuardRateLimit.workspace_id == UUID(str(workspace_id)),
            GuardRateLimit.agent_identity_id == agent_identity_id,
        ).all() if agent_identity_id else []
    except Exception:
        log.warning("gateway.profile_rate_limits.lookup_unavailable", workspace_id=workspace_id)
        return ProfileRateDecision(True, "Profile rate limits unavailable; retry later.",
                                   "availability", status=503, retry_after=retry_after)

    minute = int(time.time() // 60)
    # Retain the admitted window through retries and long streams. The minute
    # suffix still gives every new window an independent counter.
    keys, arguments, buckets, token_keys = [], [7200], [], []
    reserved_tokens = max(0, reserved_tokens)
    for scope, row in [("profile", r) for r in rows] + [("agent", r) for r in agent_rows]:
        # Workspace hash tags allow atomic admission across profiles and agents.
        subject = f"profile:{profile_id}" if scope == "profile" else f"agent:{agent_identity_id}"
        prefix = f"guard:prl:{{{workspace_id}}}:{subject}"
        for metric, cap, amount in (("rpm", row.rpm, 1), ("tpm", row.tpm, reserved_tokens)):
            if cap is None:
                continue
            key = f"{prefix}:{metric}:{minute}"
            keys.append(key)
            arguments.extend((cap, amount))
            buckets.append((metric, cap, scope))
            if metric == "tpm":
                token_keys.append(key)
    if not keys:
        return ProfileRateDecision()
    try:
        result = _redis_client().register_script(_ADMIT)(keys=keys, args=arguments)
        if not result[0]:
            metric, cap, scope = buckets[int(result[1]) - 1]
            label = "Requests" if metric == "rpm" else "Tokens"
            return ProfileRateDecision(True, f"{label}-per-minute limit of {cap} reached.",
                                       metric, cap, int(result[2]), scope,
                                       retry_after=retry_after)
    except Exception:
        log.warning("gateway.profile_rate_limits.redis_unavailable", workspace_id=workspace_id)
        return ProfileRateDecision(True, "Rate-limit service unavailable; retry later.",
                                   "availability", status=503, retry_after=retry_after)
    return ProfileRateDecision(admission=ProfileRateAdmission(reserved_tokens, token_keys))


def _tokens(payload: bytes, operation: str) -> tuple[int, bool]:
    if operation == "anthropic_count_tokens":
        try:
            count = json.loads(payload)["input_tokens"]
            if type(count) is int and count >= 0:
                return count, True
        except (ValueError, KeyError, TypeError):
            pass
        return 0, False
    family = {
        "anthropic_messages": ProviderFamily.ANTHROPIC_MESSAGES,
        "openai_responses": ProviderFamily.OPENAI_RESPONSES,
    }.get(operation, ProviderFamily.OPENAI_CHAT)
    # A translated SDK fallback can capture a different provider wire shape.
    # Use its complete usage, not the caller's protocol assumption.
    best = 0
    for candidate in dict.fromkeys([family, *ProviderFamily]):
        usage = normalize_sse(candidate, payload) if b"data:" in payload else normalize_json(candidate, payload)
        tokens = usage.tokens
        count = max(0, tokens.total_input_tokens or 0) + max(0, tokens.total_output_tokens or 0)
        if usage.completeness == UsageCompleteness.COMPLETE:
            return count, True
        best = max(best, count)
    return best, False


def actual_profile_tokens(plan, reserved_tokens: int) -> int:
    """Count raw provider usage, including paid failures before a fallback."""
    if not plan or not plan.last_meta.get("attempts"):
        return reserved_tokens if getattr(plan, "dispatched", False) else 0
    total, complete = 0, True
    for attempt in plan.last_meta["attempts"]:
        if attempt.get("error_class") == "PolicyBlock":
            continue
        payload = bytes(plan.upstream_body) if attempt.get("succeeded") else b""
        if not payload and attempt.get("response_bytes_b64"):
            try:
                payload = base64.b64decode(attempt["response_bytes_b64"], validate=True)
            except ValueError:
                pass
        if not payload:
            complete = False
            continue
        try:
            count, measured = _tokens(payload, attempt.get("operation") or plan.operation)
        except Exception:
            count, measured = 0, False
        total += count
        complete = complete and measured
    # Missing/interrupted usage cannot refund the reservation or discard known
    # usage that already exceeded it.
    return total if complete else max(total, reserved_tokens)


def settle_profile_rate_limit(admission: ProfileRateAdmission, plan) -> None:
    if admission.finished:
        return
    admission.finished = True
    if not admission.token_keys:
        return
    actual = actual_profile_tokens(plan, admission.reserved_tokens)
    try:
        _redis_client().register_script(_SETTLE)(
            keys=admission.token_keys, args=[actual - admission.reserved_tokens],
        )
    except Exception:
        # A failed settlement keeps the original reservation, never refunds it.
        log.warning("gateway.profile_rate_limits.settlement_unavailable")


async def finish_profile_rate_limit(admission: ProfileRateAdmission, plan) -> None:
    import anyio
    from starlette.concurrency import run_in_threadpool
    with anyio.CancelScope(shield=True):
        await run_in_threadpool(settle_profile_rate_limit, admission, plan)


def wrap_profile_rate_stream(response, admission: ProfileRateAdmission, plan):
    original = response.body_iterator

    async def iterator():
        try:
            async for chunk in original:
                yield chunk
        finally:
            import anyio
            with anyio.CancelScope(shield=True):
                try:
                    close = getattr(original, "aclose", None)
                    if close:
                        await close()
                finally:
                    await finish_profile_rate_limit(admission, plan)

    response.body_iterator = iterator()
    return response
