"""Workspace router — rename and lightweight CRUD.

PATCH /workspaces/{workspace_id} — rename workspace.
"""
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _user_can_edit(db: Session, workspace_id: str, user_id: str) -> bool:
    """Caller is owner or member of the workspace."""
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if ws and ws.owner_id == user_id:
        return True
    return (
        db.query(WorkspaceUser)
        .filter(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.clerk_user_id == user_id,
        )
        .first()
        is not None
    )


@router.patch("/{workspace_id}")
def rename_workspace(
    workspace_id: str,
    body: dict,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    if not _user_can_edit(db, workspace_id, user_id):
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    ws.name = name
    db.commit()
    log.info("workspace.renamed", workspace_id=workspace_id, by=user_id)
    return {"id": str(ws.id), "name": ws.name}
