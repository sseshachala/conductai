"""
Guard team management endpoints.

POST   /guard/teams                                  — create team (returns team + invite_code)
GET    /guard/teams/me                               — get my team (by conductai_workspace_id header)
POST   /guard/teams/join                             — join via invite code
GET    /guard/teams/{team_id}/members                — list active members
PATCH  /guard/teams/{team_id}/members/{member_id}   — update role (owner|security|developer)
DELETE /guard/teams/{team_id}/members/{member_id}   — soft-delete (active=False)
POST   /guard/teams/{team_id}/invite/regenerate     — generate new invite code
"""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.modules.guard.models import GuardMember, GuardTeam

router = APIRouter(prefix="/guard/teams", tags=["guard-teams"])

_VALID_ROLES = {"owner", "security", "developer"}


# ── Pydantic models ────────────────────────────────────────────────────────────

class TeamCreate(BaseModel):
    name: str


class TeamJoin(BaseModel):
    invite_code: str
    email: str
    user_id: str


class MemberPatch(BaseModel):
    role: str


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    team_id: uuid.UUID
    user_id: str
    email: str
    role: str
    active: bool
    joined_at: datetime | None


class TeamOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    invite_code: str
    conductai_workspace_id: str | None
    created_at: datetime
    updated_at: datetime


# ── Helpers ────────────────────────────────────────────────────────────────────

def _unique_slug(db: Session, name: str) -> str:
    base = name.lower().replace(" ", "-")[:50]
    slug = base
    n = 2
    while db.query(GuardTeam).filter(GuardTeam.slug == slug).first():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _new_invite_code() -> str:
    return secrets.token_urlsafe(16)


def _get_team_or_404(db: Session, team_id: str) -> GuardTeam:
    try:
        tid = uuid.UUID(team_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Team not found")
    team = db.query(GuardTeam).filter(GuardTeam.id == tid).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


def _get_member_or_404(db: Session, team_id: uuid.UUID, member_id: str) -> GuardMember:
    try:
        mid = uuid.UUID(member_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Member not found")
    member = (
        db.query(GuardMember)
        .filter(GuardMember.id == mid, GuardMember.team_id == team_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("", response_model=TeamOut, status_code=201)
def create_team(
    body: TeamCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Create a new guard team for the authenticated workspace."""
    slug = _unique_slug(db, body.name)
    team = GuardTeam(
        name=body.name,
        slug=slug,
        invite_code=_new_invite_code(),
        conductai_workspace_id=workspace_id,
    )
    db.add(team)
    db.commit()
    db.refresh(team)
    return team


@router.get("/me", response_model=TeamOut)
def get_my_team(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return the team associated with the caller's workspace."""
    team = (
        db.query(GuardTeam)
        .filter(GuardTeam.conductai_workspace_id == workspace_id)
        .first()
    )
    if not team:
        raise HTTPException(status_code=404, detail="No team found for this workspace")
    return team


@router.post("/join", response_model=MemberOut, status_code=201)
def join_team(
    body: TeamJoin,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Join a team using an invite code. 409 if the user is already an active member."""
    team = db.query(GuardTeam).filter(GuardTeam.invite_code == body.invite_code).first()
    if not team:
        raise HTTPException(status_code=404, detail="Invalid invite code")

    existing = (
        db.query(GuardMember)
        .filter(
            GuardMember.team_id == team.id,
            GuardMember.user_id == body.user_id,
            GuardMember.active.is_(True),
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="User is already an active member of this team")

    member = GuardMember(
        team_id=team.id,
        user_id=body.user_id,
        email=body.email,
        role="developer",
        active=True,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{team_id}/members", response_model=list[MemberOut])
def list_members(
    team_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return all active members for a team."""
    team = _get_team_or_404(db, team_id)
    return (
        db.query(GuardMember)
        .filter(GuardMember.team_id == team.id, GuardMember.active.is_(True))
        .all()
    )


@router.patch("/{team_id}/members/{member_id}", response_model=MemberOut)
def update_member_role(
    team_id: str,
    member_id: str,
    body: MemberPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Update a member's role. Valid roles: owner, security, developer."""
    if body.role not in _VALID_ROLES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{body.role}'. Must be one of: {sorted(_VALID_ROLES)}",
        )
    team = _get_team_or_404(db, team_id)
    member = _get_member_or_404(db, team.id, member_id)
    member.role = body.role
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{team_id}/members/{member_id}", status_code=204)
def remove_member(
    team_id: str,
    member_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Soft-delete a member by setting active=False."""
    team = _get_team_or_404(db, team_id)
    member = _get_member_or_404(db, team.id, member_id)
    member.active = False
    db.commit()


@router.post("/{team_id}/invite/regenerate", response_model=TeamOut)
def regenerate_invite(
    team_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Invalidate the current invite code and generate a new one."""
    team = _get_team_or_404(db, team_id)
    team.invite_code = _new_invite_code()
    team.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(team)
    return team
