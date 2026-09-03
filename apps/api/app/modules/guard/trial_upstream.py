"""Trial-only platform upstream fallback (epic #1567 PR 2).

When a workspace on `plan='free_trial'` sends a proxy request authenticated by
its trial `AgentIdentity` and has no vault key, this module returns the
platform-funded key from `GUARD_TRIAL_ANTHROPIC_KEY` (Render env). Any other
empty-vault case stays fail-closed at proxy.py.

The trial branch is fenced by:
- workspace.plan == 'free_trial'
- provider == 'anthropic'  (only provider funded today; add later if needed)
- agent_identity is the trial identity (name matches, unexpired, active)
- vault is empty (caller already checked; enforced by call-site position)
- request-count cap: at most `TRIAL_DAILY_CAP` proxy requests per workspace
  per 24h, counted from `guard_audit_events` (cheap; post-response but the
  fence is checked *before* handing out the key)

Returns `(key, status)`:
- `("<env-key>", "active")` — hand this to the caller as `real_key`
- `(None, "expired")`      — trial identity past `expires_at`
- `(None, "exceeded")`     — trial cap already hit for today
- `(None, "ineligible")`   — any gate not met (wrong plan, wrong provider,
                              not the trial identity, env var missing)
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Literal

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, TRIAL_PLAN

log = structlog.get_logger(__name__)

GUARD_TRIAL_ANTHROPIC_KEY_ENV = "GUARD_TRIAL_ANTHROPIC_KEY"
TRIAL_DAILY_CAP = 200
TRIAL_CAP_WINDOW_HOURS = 24
TrialStatus = Literal["active", "expired", "exceeded", "ineligible"]


def _redis_client():
    """Same shape as `app.modules.guard.rate_limit._redis_client` — lazy
    import so tests can monkeypatch and the module loads without redis."""
    import redis as _redis
    from app.core.config import settings as _settings
    return _redis.from_url(_settings.redis_url, decode_responses=True)


def try_reserve_trial_slot(workspace_id: str, agent_identity_id: str) -> bool:
    """Atomically reserve a slot in today's trial-cap window.

    Uses Redis INCR (single-command atomic) so two concurrent requests
    can't both pass the `< CAP` check. Returns True if the request is
    under cap after the reservation, False if the reservation put us at
    or over cap (caller should return 'exceeded').

    Fails open when Redis is unreachable: logs a warning and returns True.
    Rate-limit convention across the codebase (see `rate_limit.py`) — a
    Redis outage shouldn't defeat trial availability, and the per-workspace
    `guard_spend_budgets.hard_limit_usd = $2` cap bounds abuse anyway.
    """
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    key = f"guard:trial:cap:{workspace_id}:{agent_identity_id}:{day}"
    try:
        r = _redis_client()
        pipe = r.pipeline()
        pipe.incr(key, 1)
        pipe.expire(key, TRIAL_CAP_WINDOW_HOURS * 3600)
        count, _ = pipe.execute()
        return int(count or 0) <= TRIAL_DAILY_CAP
    except Exception as exc:  # noqa: BLE001
        log.warning(
            "guard.trial.reserve_redis_unavailable",
            workspace_id=workspace_id,
            err=str(exc),
        )
        return True


def get_trial_cap_used(db: Session, workspace_id: str, agent_identity_id: str) -> int:
    """Count trial-identity audit rows in the last `TRIAL_CAP_WINDOW_HOURS`.

    Single source of truth for the trial cap counter — the proxy fence in
    `resolve_trial_key` and the read-out in `/guard/trial/session` both call
    this so the window/columns can't drift between call sites.
    """
    now = datetime.now(timezone.utc)
    return db.execute(
        text("""
            SELECT COUNT(*) FROM guard_audit_events
            WHERE workspace_id = :ws
              AND agent_identity_id = :aid
              AND ts >= :cutoff
        """),
        {
            "ws": str(workspace_id),
            "aid": str(agent_identity_id),
            "cutoff": now - timedelta(hours=TRIAL_CAP_WINDOW_HOURS),
        },
    ).scalar() or 0


def resolve_trial_key(
    db: Session,
    workspace_id: str,
    provider: str,
    agent_identity_id: str | None,
) -> tuple[str | None, TrialStatus]:
    """Trial-only platform upstream key resolver. See module docstring."""
    if provider != "anthropic":
        return None, "ineligible"

    env_key = os.environ.get(GUARD_TRIAL_ANTHROPIC_KEY_ENV) or ""
    if not env_key:
        return None, "ineligible"

    if not agent_identity_id:
        return None, "ineligible"

    row = db.execute(
        text("""
            SELECT ai.expires_at, ai.lifecycle_state, ai.name, w.plan
            FROM agent_identities ai
            JOIN workspaces w ON w.id = ai.workspace_id
            WHERE ai.id = :aid AND ai.workspace_id = :ws
            LIMIT 1
        """),
        {"aid": agent_identity_id, "ws": str(workspace_id)},
    ).fetchone()
    if row is None:
        return None, "ineligible"
    if row.plan != TRIAL_PLAN:
        return None, "ineligible"
    if row.name != TRIAL_IDENTITY_NAME:
        return None, "ineligible"
    if row.lifecycle_state != "active":
        return None, "ineligible"

    now = datetime.now(timezone.utc)
    if row.expires_at is None or row.expires_at <= now:
        return None, "expired"

    # #1587 A4: race-free cap check via Redis atomic INCR. Falls back to
    # DB count (with the original race) only when Redis is unreachable.
    if not try_reserve_trial_slot(str(workspace_id), agent_identity_id):
        return None, "exceeded"
    # Belt+braces: DB count catches Redis-outage windows AND deliberate
    # Redis resets (e.g. ops flushed the bucket mid-day). `>= CAP` matches
    # the original pre-A4 semantic so a workspace that has already
    # completed CAP requests stays rejected even if the Redis bucket says
    # otherwise. Cheap SUM against indexed columns.
    if get_trial_cap_used(db, workspace_id, agent_identity_id) >= TRIAL_DAILY_CAP:
        return None, "exceeded"

    # #1587 A3: opportunistic Slack alert on aggregate trial-key spend.
    # Fires from here so the check piggybacks on real trial traffic instead
    # of needing a cron. Rate-limited + threshold-gated inside the alerter;
    # never raises (guarded by trial_spend_alert itself).
    from app.modules.guard.observability.trial_spend_alert import check_and_alert_trial_spend
    check_and_alert_trial_spend(db)

    return env_key, "active"
