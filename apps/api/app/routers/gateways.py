"""Retired v1 Gateway management surface; persisted profile data is untouched."""
from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import get_workspace_id, require_permission

router = APIRouter(prefix="/workspaces", tags=["gateway-profiles-retired"])


def _retired(workspace_id: str, scoped_ws_id: str) -> None:
    if str(workspace_id) != str(scoped_ws_id):
        raise HTTPException(status_code=403, detail="Workspace mismatch")
    raise HTTPException(status_code=410, detail={
        "code": "gateway_v1_retired",
        "message": "Use Gateway Profile v2 draft and publish APIs.",
        "replacement": f"/workspaces/{workspace_id}/gateway-profiles-v2",
    })


@router.get("/{workspace_id}/gateways")
@router.get("/{workspace_id}/gateways/{gateway_id}")
def retired_gateway_read(
    workspace_id: str,
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    _retired(workspace_id, scoped_ws_id)


@router.post("/{workspace_id}/gateways")
@router.post("/{workspace_id}/gateways/validate")
@router.put("/{workspace_id}/gateways/{gateway_id}")
@router.delete("/{workspace_id}/gateways/{gateway_id}")
def retired_gateway_write(
    workspace_id: str,
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    _retired(workspace_id, scoped_ws_id)


@router.post("/{workspace_id}/gateways/{gateway_id}/push")
def retired_gateway_push(
    workspace_id: str,
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    _retired(workspace_id, scoped_ws_id)
