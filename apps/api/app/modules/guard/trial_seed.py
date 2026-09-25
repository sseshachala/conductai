"""Trial seed for new signups (epic #1567).

Called from the Clerk `user.created` webhook and from `/theguard/try` first-hit
(shipped in a later PR). Idempotent — safe to replay.

Sets `workspaces.plan='free_trial'`, inserts a workspace-default
`guard_rate_limits` row, inserts a workspace-default `guard_spend_budgets`
row, and mints a 7-day trial `AgentIdentity`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.crypto import encrypt
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.router import _generate_token

TRIAL_PLAN = "free_trial"
TRIAL_RPM = 60
TRIAL_TPM = 100_000
TRIAL_MONTHLY_USD = 2.0
TRIAL_HARD_USD = 2.0
TRIAL_DAYS = 7
TRIAL_IDENTITY_NAME = "Trial (7 days)"


def link_trial_owner(db: Session, workspace_id: str, identity_id: str) -> None:
    """Repair only an unlinked, active owner membership; never undo revocation."""
    # A member may already have a normal CLI identity. Bind the trial
    # independently rather than replacing that identity or its sessions.
    db.execute(text("""
        UPDATE agent_identities AS identity
        SET owner_user_id = workspace.owner_id
        FROM workspaces AS workspace, workspace_users AS membership,
             guard_member_config AS member
        WHERE workspace.id = :ws
          AND identity.id = :aid AND identity.workspace_id = workspace.id
          AND identity.source = 'conduct_trial'
          AND identity.owner_user_id IS NULL
          AND identity.lifecycle_state = 'active' AND identity.expires_at > now()
          AND membership.workspace_id = workspace.id
          AND membership.clerk_user_id = workspace.owner_id
          AND member.workspace_id = workspace.id
          AND member.clerk_user_id = workspace.owner_id AND member.active = true
    """), {"ws": str(workspace_id), "aid": str(identity_id)})
    db.execute(text("""
        UPDATE guard_member_config AS member
        SET agent_identity_id = :aid
        FROM workspaces AS workspace, workspace_users AS membership,
             agent_identities AS identity
        WHERE workspace.id = :ws
          AND member.workspace_id = workspace.id
          AND member.clerk_user_id = workspace.owner_id
          AND membership.workspace_id = workspace.id
          AND membership.clerk_user_id = member.clerk_user_id
          AND member.active = true AND member.agent_identity_id IS NULL
          AND identity.id = :aid AND identity.workspace_id = workspace.id
          AND identity.source = 'conduct_trial'
          AND identity.lifecycle_state = 'active'
          AND identity.expires_at > now()
    """), {"ws": str(workspace_id), "aid": str(identity_id)})


def seed_trial(db: Session, workspace_id: str) -> str | None:
    """Seed trial guardrails on `workspace_id`. Idempotent.

    Returns the plaintext trial token if a new identity was minted, else None.
    Caller commits.
    """
    now = datetime.now(timezone.utc)
    ws = str(workspace_id)

    # Only flip fresh workspaces to `free_trial`. Never overwrite an active
    # workspace's plan (PR 4 cohort-2 fix). Idempotent replays are a no-op
    # since the plan is already `free_trial`.
    db.execute(
        text("UPDATE workspaces SET plan = :plan WHERE id = :ws AND plan = 'free'"),
        {"plan": TRIAL_PLAN, "ws": ws},
    )

    # ponytail: NULLs are distinct in the guard_rate_limits unique constraint,
    # so ON CONFLICT won't fire for workspace-default rows. Use WHERE NOT EXISTS.
    db.execute(
        text("""
            INSERT INTO guard_rate_limits (id, workspace_id, agent_identity_id, rpm, tpm, created_at, updated_at)
            SELECT gen_random_uuid(), :ws, NULL, :rpm, :tpm, :now, :now
            WHERE NOT EXISTS (
                SELECT 1 FROM guard_rate_limits
                WHERE workspace_id = :ws AND agent_identity_id IS NULL
            )
        """),
        {"ws": ws, "rpm": TRIAL_RPM, "tpm": TRIAL_TPM, "now": now},
    )

    db.execute(
        text("""
            INSERT INTO guard_spend_budgets (id, workspace_id, clerk_user_id, monthly_limit_usd, hard_limit_usd, alert_threshold_pct, created_at, updated_at)
            SELECT gen_random_uuid(), :ws, NULL, :monthly, :hard, 80, :now, :now
            WHERE NOT EXISTS (
                SELECT 1 FROM guard_spend_budgets
                WHERE workspace_id = :ws AND clerk_user_id IS NULL
            )
        """),
        {"ws": ws, "monthly": TRIAL_MONTHLY_USD, "hard": TRIAL_HARD_USD, "now": now},
    )

    existing = db.execute(
        text("""
            SELECT 1 FROM agent_identities
            WHERE workspace_id = :ws AND name = :name
              AND lifecycle_state = 'active'
              AND (expires_at IS NULL OR expires_at > :now)
            LIMIT 1
        """),
        {"ws": ws, "name": TRIAL_IDENTITY_NAME, "now": now},
    ).fetchone()
    if existing:
        return None

    plaintext, prefix = _generate_token()
    identity_id = str(uuid.uuid4())
    db.add(AgentIdentity(
        id=identity_id,
        workspace_id=workspace_id,
        name=TRIAL_IDENTITY_NAME,
        provider="conduct",
        source="conduct_trial",
        token_prefix=prefix,
        token_encrypted=encrypt({"token": plaintext}),
        environment_id=None,
        created_at=now,
        last_used_at=None,
        expires_at=now + timedelta(days=TRIAL_DAYS),
    ))
    db.flush()
    link_trial_owner(db, workspace_id, identity_id)
    return plaintext
