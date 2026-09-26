"""Workspace Lens credential selection; values never cross the settings API."""
from uuid import UUID

from fastapi import HTTPException

from app.models.environment import Environment
from app.models.workspace import Workspace

PREFERENCE = "lens_environment_id"


def selected_environment(db, workspace_id):
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if workspace is None:
        raise HTTPException(404, "Workspace not found")
    selected = (workspace.preferences or {}).get(PREFERENCE)
    if selected:
        try:
            selected = UUID(str(selected))
        except ValueError:
            raise HTTPException(409, "Lens Vault selection is invalid. Choose a Vault in Lens settings.") from None
        require_environment(db, workspace_id, selected)
    return selected


def require_environment(db, workspace_id, environment_id):
    row = db.query(Environment).filter(
        Environment.id == environment_id, Environment.workspace_id == workspace_id,
    ).first()
    if row is None:
        raise HTTPException(404, "Selected Lens Vault is unavailable. Choose a Vault in Lens settings.")
    return row


def save_environment(db, workspace_id, environment_id):
    require_environment(db, workspace_id, environment_id)
    workspace = db.query(Workspace).filter(Workspace.id == workspace_id).with_for_update().first()
    if workspace is None:
        raise HTTPException(404, "Workspace not found")
    workspace.preferences = {**(workspace.preferences or {}), PREFERENCE: str(environment_id)}
    db.commit()
