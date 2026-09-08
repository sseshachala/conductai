"""Shared workspace-onboarding path (#1712 Track 1 PR 5 unification).

One function creates a fully-onboarded workspace for a Clerk user:
workspace + membership + guard_config + guard_member_config + starter
policies + trial. Called from two places today:

- Clerk `user.created` webhook (browser signup flow)
- `/guard/trial/provision` endpoint (curl-install flow)

Any future entrypoint (SSO auto-provisioning, org invitation acceptance,
etc.) should call this function too — the goal is to have exactly one
"new user, first workspace" code path across all surfaces so trial
guarantees, starter policy set, and audit-chain seeding never diverge.
"""
from __future__ import annotations

import secrets as _secrets
import uuid as _uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


def provision_workspace_for_user(
    db: Session,
    clerk_user_id: str,
    *,
    name: str = "Engineering",
) -> _uuid.UUID:
    """Create a workspace for a new Clerk user, or return the existing one.

    Idempotent — if the user already owns a workspace, returns its id
    without re-seeding (matches the webhook's "workspace already exists"
    early-return). Caller is responsible for `db.commit()` so this can
    compose into larger transactions.

    Returns the workspace id.
    """
    # `owner_id` should be unique per Clerk user in normal operation. Multi-row
    # matches indicate either legacy manual inserts or a race we didn't
    # catch — surface them so ops can investigate. We still return the
    # oldest (`created_at ASC`) for deterministic idempotency.
    existing_rows = db.execute(
        text("SELECT id FROM workspaces WHERE owner_id = :uid ORDER BY created_at ASC"),
        {"uid": clerk_user_id},
    ).fetchall()
    if existing_rows:
        if len(existing_rows) > 1:
            log.warning(
                "onboarding.multiple_workspaces_for_owner",
                clerk_user_id=clerk_user_id,
                count=len(existing_rows),
                ids=[str(r.id) for r in existing_rows],
                note="returning oldest for idempotency; investigate root cause",
            )
        winner = existing_rows[0]
        log.info("onboarding.workspace_exists", clerk_user_id=clerk_user_id, workspace_id=str(winner.id))
        return winner.id

    now = datetime.now(timezone.utc)
    workspace_id = _uuid.uuid4()
    invite_code = _uuid.uuid4().hex[:16]
    member_token = _secrets.token_urlsafe(24)

    db.execute(
        text("""
            INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
            VALUES (:id, :name, :owner_id, 'free', true, :now, :now)
            ON CONFLICT DO NOTHING
        """),
        {"id": str(workspace_id), "name": name or "Engineering", "owner_id": clerk_user_id, "now": now},
    )
    db.execute(
        text("""
            INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
            VALUES (:ws, :uid, 'admin', :now)
            ON CONFLICT DO NOTHING
        """),
        {"ws": str(workspace_id), "uid": clerk_user_id, "now": now},
    )
    db.execute(
        text("""
            INSERT INTO guard_config (workspace_id, invite_code, created_at)
            VALUES (:ws, :code, :now)
            ON CONFLICT (workspace_id) DO NOTHING
        """),
        {"ws": str(workspace_id), "code": invite_code, "now": now},
    )
    db.execute(
        text("""
            INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
            VALUES (:ws, :uid, :token, true, :now)
            ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
        """),
        {"ws": str(workspace_id), "uid": clerk_user_id, "token": member_token, "now": now},
    )

    # Starter Guard policies (packs + defaults). Imported lazily because
    # projects.py depends on app.core.database which imports back into us
    # transitively via the models package.
    from app.routers.projects import _seed_starter_policies
    _seed_starter_policies(db, workspace_id, now)

    # Trial seed (#1567) — rate/budget caps + 7-day trial agent identity.
    from app.modules.guard.trial_seed import seed_trial
    seed_trial(db, str(workspace_id))

    log.info("onboarding.workspace_created", clerk_user_id=clerk_user_id, workspace_id=str(workspace_id))
    return workspace_id
