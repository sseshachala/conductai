"""
Projects (workspaces) CRUD + template listing + member management.

A "project" is a workspace. Users belong to workspaces via workspace_users
(many-to-many with per-workspace roles). All signed-in users get immediate
access — the workspace_users table is the access gate.
"""
import hmac
from typing import Annotated

import structlog
log = structlog.get_logger(__name__)

from fastapi import Depends, Header, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.routers.projects_members import router

# Re-exported for callers that import these names from this module.
from app.routers.projects_core import (  # noqa: E402,F401
    _audit,
    _seed_starter_policies,
    _send_clerk_invite,
)
from app.routers.projects_members import (  # noqa: E402,F401
    list_members,
)


# ---------------------------------------------------------------------------
# Admin — approve a user by owner_id or workspace id
# Protected by X-Admin-Secret header matching ADMIN_SECRET env var
# ---------------------------------------------------------------------------

@router.post("/admin/approve", status_code=200)
def admin_approve(
    body: dict,
    x_admin_secret: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    if not settings.admin_secret or not hmac.compare_digest(x_admin_secret or "", settings.admin_secret):
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    owner_id = body.get("owner_id")
    workspace_id = body.get("workspace_id")

    if not owner_id and not workspace_id:
        raise HTTPException(status_code=422, detail="Provide owner_id or workspace_id")

    if owner_id:
        result = db.execute(text(
            "UPDATE workspaces SET is_approved = true WHERE owner_id = :oid RETURNING id, name"
        ), {"oid": owner_id})
    else:
        result = db.execute(text(
            "UPDATE workspaces SET is_approved = true WHERE id = :wid RETURNING id, name"
        ), {"wid": workspace_id})

    rows = result.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No workspaces found")

    db.commit()
    return {"approved": [{"id": str(r.id), "name": r.name} for r in rows]}
