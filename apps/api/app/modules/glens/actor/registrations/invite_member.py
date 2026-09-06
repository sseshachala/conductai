"""#1301 — Lens actor: invite a new workspace member by email.

Two-step: `propose` validates the email + role, rejects if already a
member or has a pending invite. `execute` inserts the `workspace_invites`
row, fires the Clerk org invitation, and sends the templated email — the
same fanout as `POST /projects/{ws}/members` uses (`invite_member` is a
thin wrapper over that endpoint's helpers, not a parallel implementation).
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import text

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


def _propose_invite_member(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    email = str(args.get("email") or "").strip().lower()
    role = str(args.get("role") or "").strip()

    if not email or "@" not in email:
        return ProposeResult(rejected=True, reason="email required (must contain '@')",
                             summary="", resolved_input={})
    if not role:
        return ProposeResult(rejected=True, reason="role required",
                             summary="", resolved_input={})

    from app.core.auth import find_clerk_user_id_by_email, get_valid_roles

    if role not in get_valid_roles(ctx.db):
        return ProposeResult(rejected=True, reason=f"Invalid role '{role}'",
                             summary="", resolved_input={})

    ws = ctx.workspace_id

    existing_clerk_id = find_clerk_user_id_by_email(email)
    if existing_clerk_id:
        already = ctx.db.execute(text("""
            SELECT 1 FROM workspace_users
            WHERE workspace_id = :ws AND clerk_user_id = :uid
        """), {"ws": ws, "uid": existing_clerk_id}).fetchone()
        if already:
            return ProposeResult(
                rejected=True,
                reason=f"'{email}' is already a member of this workspace",
                summary="", resolved_input={},
            )

    pending = ctx.db.execute(text("""
        SELECT 1 FROM workspace_invites
        WHERE workspace_id = :ws AND invited_email = :email AND accepted_at IS NULL
    """), {"ws": ws, "email": email}).fetchone()
    if pending:
        return ProposeResult(
            rejected=True,
            reason=f"An invite for '{email}' is already pending",
            summary="", resolved_input={},
        )

    summary = f"Invite '{email}' as {role}"
    return ProposeResult(
        summary=summary,
        resolved_input={"email": email, "role": role},
    )


def _execute_invite_member(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Insert the invite row, fire the Clerk fanout + templated email.

    Uses the same helpers as `POST /projects/{ws}/members` — importing them
    keeps the two paths behavior-identical without duplicating the Clerk
    call or the email template."""
    from app.core.auth import get_clerk_user_email, get_role_description
    from app.core.config import settings
    from app.core.email import send_template_email
    from app.routers.projects import _audit, _send_clerk_invite

    email = resolved["email"]
    role = resolved["role"]
    ws = ctx.workspace_id
    inviter = ctx.clerk_user_id
    now = datetime.now(timezone.utc)

    invite_id = ctx.db.execute(text("""
        INSERT INTO workspace_invites (workspace_id, invited_email, role, invited_by, created_at)
        VALUES (:ws, :email, :role, :invited_by, :now)
        ON CONFLICT (workspace_id, invited_email)
        DO UPDATE SET role = EXCLUDED.role,
                      invited_by = EXCLUDED.invited_by,
                      created_at = EXCLUDED.created_at,
                      accepted_at = NULL
        RETURNING id
    """), {"ws": ws, "email": email, "role": role,
           "invited_by": inviter, "now": now}).fetchone()[0]

    inviter_email = get_clerk_user_email(inviter) if inviter else None
    _audit(ctx.db, workspace_id=ws, actor_id=inviter or "lens.actor",
           actor_email=inviter_email, actor_role="admin",
           action="member.invited", resource_type="invite",
           resource_id=email, meta={"role": role, "invite_id": str(invite_id),
                                    "via": "lens.actor"})
    ctx.db.commit()

    _send_clerk_invite(ctx.db, ws, email, role, invite_id=str(invite_id))

    ws_row = ctx.db.execute(text("SELECT name FROM workspaces WHERE id = :id"),
                            {"id": ws}).fetchone()
    workspace_name = ws_row.name if ws_row else "your workspace"

    email_sent = send_template_email(
        slug="workspace_invite",
        to=email,
        context={
            "workspace_name": workspace_name,
            "invited_by_email": inviter_email or "",
            "role": role,
            "role_description": get_role_description(role, ctx.db),
            "app_url": getattr(settings, "app_url", ""),
            "workspace_id": ws,
            "guard_invite_cmd": "",
        },
        workspace_id=ws,
        db=ctx.db,
    )

    return {
        "invite_id": str(invite_id),
        "email": email,
        "role": role,
        "email_sent": bool(email_sent),
        "invited": True,
    }


default_action_registry.register(ActionSpec(
    name="invite_member",
    guard_permission="platform.members.manage",
    propose=_propose_invite_member,
    execute=_execute_invite_member,
    description=(
        "Invite a new member to the workspace by email. Two-step: returns a "
        "pending action for the user to confirm; the confirm click inserts "
        "the workspace_invites row, fires the Clerk org invitation, and "
        "sends the templated email."
    ),
))
