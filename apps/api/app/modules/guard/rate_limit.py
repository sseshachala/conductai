"""Per-key RPM/TPM rate limiting (#980, Loopers parity).

Called from `_proxy` step 4d.2 (after budget check, before vault lookup).
Config lives in guard_rate_limits: (workspace_id, agent_identity_id=NULL)
row is the workspace default; per-agent overrides use their own row.

Counters live in Redis with 1-minute windows keyed on the current epoch
minute — cheap TTL cleanup, no separate reaper.

ponytail: INCR+EXPIRE has a small TOCTOU slop (a burst can overshoot by up
to N-1 concurrent callers per window). Swap to atomic Redis Lua when
throughput matters — #822 tracks that upgrade.

ponytail: fail-open on Redis outage — a broken cache should not silently
block all LLM traffic. Guard's fail-closed discipline (#823) covers policy
decisions, not soft-quota infrastructure.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session


log = structlog.get_logger(__name__)


@dataclass
class RateLimitDecision:
    limited: bool
    reason: str | None
    metric: str | None      # "rpm" | "tpm"
    limit: int | None
    current: int | None
    scope: str              # "agent" | "workspace" | "none"


def _resolve_limits(db: Session, workspace_id: str, agent_identity_id: str | None) -> tuple[int | None, int | None, str]:
    """Return (rpm, tpm, scope). Per-agent overrides win over workspace default.

    Fails open on any DB error — a missing migration or transient failure must
    not block all proxy traffic. Matches the redis fail-open posture below.
    """
    try:
        if agent_identity_id:
            row = db.execute(
                text("SELECT rpm, tpm FROM guard_rate_limits WHERE workspace_id = :ws AND agent_identity_id = :aid"),
                {"ws": workspace_id, "aid": agent_identity_id},
            ).first()
            if row and (row.rpm is not None or row.tpm is not None):
                return row.rpm, row.tpm, "agent"

        row = db.execute(
            text("SELECT rpm, tpm FROM guard_rate_limits WHERE workspace_id = :ws AND agent_identity_id IS NULL"),
            {"ws": workspace_id},
        ).first()
        if row and (row.rpm is not None or row.tpm is not None):
            return row.rpm, row.tpm, "workspace"
    except Exception as e:  # noqa: BLE001 — fail-open (see module docstring)
        # Rollback so the outer request session isn't poisoned for later queries
        # (a ProgrammingError leaves psycopg2 in "aborted transaction" state).
        try:
            db.rollback()
        except Exception:
            pass
        log.warning("guard.rate_limit.db_unavailable", err=str(e), workspace_id=workspace_id)

    return None, None, "none"


def _redis_client():
    import redis as _redis
    from app.core.config import settings as _settings
    return _redis.from_url(_settings.redis_url, decode_responses=True)


def check_rate_limit(
    db: Session,
    *,
    workspace_id: str,
    agent_identity_id: str | None,
    input_tokens: int,
) -> RateLimitDecision:
    """Increment RPM+TPM counters and return whether the request is over cap."""
    rpm, tpm, scope = _resolve_limits(db, workspace_id, agent_identity_id)
    if rpm is None and tpm is None:
        return RateLimitDecision(False, None, None, None, None, "none")

    minute = int(time.time() // 60)
    scope_id = agent_identity_id or "default"
    rpm_key = f"guard:rl:{workspace_id}:{scope_id}:rpm:{minute}"
    tpm_key = f"guard:rl:{workspace_id}:{scope_id}:tpm:{minute}"

    try:
        r = _redis_client()
        pipe = r.pipeline()
        pipe.incr(rpm_key, 1)
        pipe.expire(rpm_key, 70)
        pipe.incrby(tpm_key, max(0, input_tokens))
        pipe.expire(tpm_key, 70)
        rpm_val, _, tpm_val, _ = pipe.execute()
        rpm_val = int(rpm_val or 0)
        tpm_val = int(tpm_val or 0)
    except Exception as e:  # noqa: BLE001 — fail-open by design (see module docstring)
        log.warning("guard.rate_limit.redis_unavailable", err=str(e), workspace_id=workspace_id)
        return RateLimitDecision(False, None, None, None, None, scope)

    if rpm is not None and rpm_val > rpm:
        return RateLimitDecision(
            True,
            f"Requests-per-minute limit of {rpm} reached ({rpm_val} in current window). Retry in <60s.",
            "rpm", rpm, rpm_val, scope,
        )
    if tpm is not None and tpm_val > tpm:
        return RateLimitDecision(
            True,
            f"Tokens-per-minute limit of {tpm} reached ({tpm_val} in current window). Retry in <60s.",
            "tpm", tpm, tpm_val, scope,
        )

    return RateLimitDecision(False, None, None, None, None, scope)
