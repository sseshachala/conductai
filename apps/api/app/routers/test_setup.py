"""
Test-only router — active ONLY when TEST_SECRET env var is set.
Provides a single endpoint to create the Acme test workspace and assign members
without requiring a Clerk JWT. Protected by a shared secret header.

DO NOT include this router in production if TEST_SECRET is not set.
"""
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser

router = APIRouter(prefix="/test", tags=["test"])

TEST_SECRET = os.environ.get("TEST_SECRET", "")


def require_test_secret(x_test_secret: str = Header(default="")) -> None:
    if not TEST_SECRET or x_test_secret != TEST_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Test-Secret header")


class MemberSpec(BaseModel):
    clerk_user_id: str
    role: str  # admin | editor | security | viewer


class WorkspaceSetupRequest(BaseModel):
    workspace_name: str
    admin_clerk_user_id: str
    members: list[MemberSpec]


class WorkspaceSetupResponse(BaseModel):
    workspace_id: str
    created: bool  # True = new, False = reused existing


@router.post("/workspace-setup", response_model=WorkspaceSetupResponse)
def test_workspace_setup(
    payload: WorkspaceSetupRequest,
    _: None = Depends(require_test_secret),
    db: Session = Depends(get_db),
):
    """
    Creates (or reuses) a named test workspace and assigns members by Clerk user ID.
    Idempotent — safe to call multiple times.
    """
    # Find existing workspace by name
    existing = db.query(Workspace).filter(Workspace.name == payload.workspace_name).first()
    created = False

    if existing:
        workspace = existing
    else:
        workspace = Workspace(
            id=uuid.uuid4(),
            name=payload.workspace_name,
            owner_id=payload.admin_clerk_user_id,
            is_approved=True,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(workspace)
        db.flush()
        created = True

    # Ensure admin is a member alongside any additional members
    all_members = [
        MemberSpec(clerk_user_id=payload.admin_clerk_user_id, role="admin")
    ] + payload.members

    for member in all_members:
        existing_membership = (
            db.query(WorkspaceUser)
            .filter(
                WorkspaceUser.workspace_id == workspace.id,
                WorkspaceUser.clerk_user_id == member.clerk_user_id,
            )
            .first()
        )
        if not existing_membership:
            db.add(
                WorkspaceUser(
                    workspace_id=workspace.id,
                    clerk_user_id=member.clerk_user_id,
                    role=member.role,
                    joined_at=datetime.now(timezone.utc),
                )
            )

    db.commit()

    return WorkspaceSetupResponse(workspace_id=str(workspace.id), created=created)
