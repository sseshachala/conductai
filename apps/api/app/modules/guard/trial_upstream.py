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

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, TRIAL_PLAN

GUARD_TRIAL_ANTHROPIC_KEY_ENV = "GUARD_TRIAL_ANTHROPIC_KEY"
TRIAL_DAILY_CAP = 200
TrialStatus = Literal["active", "expired", "exceeded", "ineligible"]


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

    used = db.execute(
        text("""
            SELECT COUNT(*) FROM guard_audit_events
            WHERE workspace_id = :ws
              AND agent_identity_id = :aid
              AND ts >= :cutoff
        """),
        {"ws": str(workspace_id), "aid": agent_identity_id, "cutoff": now - timedelta(hours=24)},
    ).scalar() or 0
    if used >= TRIAL_DAILY_CAP:
        return None, "exceeded"

    return env_key, "active"
