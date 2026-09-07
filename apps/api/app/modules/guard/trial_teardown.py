"""Trial teardown on real-provider connect (epic #1587 Round C).

When a workspace on `plan='free_trial'` saves a real LLM-provider credential
via `POST /credentials`, the trial has done its job. Deactivate the trial
identity, drop the workspace-default rate-limit + spend-budget rows minted
by `trial_seed.seed_trial`, and flip the plan back to `free`. Idempotent:
safe to call on a workspace that never had a trial or has already been torn
down. Never raises — a teardown failure must not block the credential save.

The provider set starts at just `anthropic` — the only provider funded by
`GUARD_TRIAL_ANTHROPIC_KEY` today. When Round D adds funded upstreams for
other providers (openai, groq, ...), add each to `TRIAL_TEARDOWN_PROVIDERS`
so connecting them also ends the trial.
"""
from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME, TRIAL_PLAN

log = structlog.get_logger(__name__)

# Services whose real-key connect signals "the trial has done its job".
# Grows with Round D as funded upstreams land for more providers.
TRIAL_TEARDOWN_PROVIDERS: set[str] = {"anthropic"}


def teardown_trial(db: Session, workspace_id: str) -> bool:
    """Deactivate any active trial artifacts on `workspace_id`. Idempotent.

    Returns True if any row was actually changed, False if the workspace had
    nothing to tear down (never on trial, or already torn down). Caller
    commits. Never raises.
    """
    ws = str(workspace_id)
    changed = False
    try:
        plan_res = db.execute(
            text("UPDATE workspaces SET plan = 'free' WHERE id = :ws AND plan = :trial"),
            {"ws": ws, "trial": TRIAL_PLAN},
        )
        if plan_res.rowcount:
            changed = True

        id_res = db.execute(
            text("""
                UPDATE agent_identities
                SET lifecycle_state = 'expired'
                WHERE workspace_id = :ws
                  AND name = :name
                  AND lifecycle_state = 'active'
            """),
            {"ws": ws, "name": TRIAL_IDENTITY_NAME},
        )
        if id_res.rowcount:
            changed = True

        rl_res = db.execute(
            text("""
                DELETE FROM guard_rate_limits
                WHERE workspace_id = :ws AND agent_identity_id IS NULL
            """),
            {"ws": ws},
        )
        if rl_res.rowcount:
            changed = True

        sb_res = db.execute(
            text("""
                DELETE FROM guard_spend_budgets
                WHERE workspace_id = :ws AND clerk_user_id IS NULL
            """),
            {"ws": ws},
        )
        if sb_res.rowcount:
            changed = True

        if changed:
            log.info("guard.trial.torn_down", workspace_id=ws)
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.trial.teardown_failed", workspace_id=ws, err=str(exc))
        return False
    return changed


def sweep_expired_trials(db: Session) -> int:
    """Tear down trials whose identity `expires_at` has passed. Idempotent.

    Returns count of workspaces torn down. Called by the worker daemon on a
    periodic interval. Never raises.
    """
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    try:
        rows = db.execute(
            text(
                """
                SELECT DISTINCT workspace_id
                FROM agent_identities
                WHERE name = :name
                  AND lifecycle_state = 'active'
                  AND expires_at IS NOT NULL
                  AND expires_at < :now
                """
            ),
            {"name": TRIAL_IDENTITY_NAME, "now": now},
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.trial.sweep_query_failed", err=str(exc))
        return 0

    torn = 0
    for (ws_id,) in rows:
        if teardown_trial(db, str(ws_id)):
            torn += 1
    if torn:
        db.commit()
        log.info("guard.trial.sweep_swept", count=torn)
    return torn
