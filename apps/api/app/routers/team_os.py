"""
Team OS AI Rollout API — workspace-level AI instructions management.

GET  /team-os/instructions              — read instructions for workspace
POST /team-os/instructions              — publish new instructions (admin)
GET  /team-os/instructions/version      — lightweight version check (CLI staleness)
GET  /team-os/instructions/adoption     — per-member sync status (admin)
"""
import re
import uuid
from datetime import datetime, timezone, timedelta

import structlog

log = structlog.get_logger(__name__)

from pathlib import Path as _Path
DEFAULT_INSTRUCTIONS = (_Path(__file__).parent.parent / "templates" / "team_instructions_default.md").read_text().strip()


from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import (
    get_workspace_id,
    get_user_id,
    require_permission,
    get_clerk_user_email,
)
from app.core.database import get_db

router = APIRouter(prefix="/team-os", tags=["team-os"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class InstructionsOut(BaseModel):
    content: str
    version: str
    updated_at: datetime | None
    updated_by: str | None


class InstructionsIn(BaseModel):
    content: str


class VersionOut(BaseModel):
    version: str
    updated_at: str | None


class AdoptionMember(BaseModel):
    email: str
    tools: list[str]
    last_synced: str | None
    version: str | None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _bump_version(current: str) -> str:
    """Parse 'vN' → 'v(N+1)'. Falls back to 'v2' if format is unexpected."""
    match = re.fullmatch(r"v(\d+)", current or "v1")
    if match:
        return f"v{int(match.group(1)) + 1}"
    return "v2"


def _get_instructions(db: Session, workspace_id: str) -> InstructionsOut:
    """Fetch instruction row or return empty defaults."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return InstructionsOut(content=DEFAULT_INSTRUCTIONS, version="v0", updated_at=None, updated_by=None)

    row = db.execute(
        text("""
            SELECT content, version, updated_at, updated_by
            FROM workspace_instructions
            WHERE workspace_id = :ws
            LIMIT 1
        """),
        {"ws": ws_uuid},
    ).fetchone()

    if not row:
        return InstructionsOut(
            content=DEFAULT_INSTRUCTIONS,
            version="v1",
            updated_at=None,
            updated_by=None,
        )

    return InstructionsOut(
        content=row.content,
        version=row.version,
        updated_at=row.updated_at,
        updated_by=row.updated_by,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/instructions", response_model=InstructionsOut)
def get_instructions(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _user_id: str = Depends(get_user_id),
):
    """Return current AI rollout instructions for the workspace.
    Available to all authenticated workspace members.
    If no instructions have been published yet, returns empty defaults.
    """
    return _get_instructions(db, workspace_id)


@router.post("/instructions", response_model=InstructionsOut)
def publish_instructions(
    body: InstructionsIn,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("guard.settings.edit")),
):
    """Publish (upsert) new AI rollout instructions for the workspace.
    Bumps the semantic version counter and records the publishing admin.
    Requires guard.settings.edit permission (admin).
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    user_email = get_clerk_user_email(user_id)
    now = datetime.now(timezone.utc)

    # Fetch current version to bump it
    existing = db.execute(
        text("SELECT version FROM workspace_instructions WHERE workspace_id = :ws LIMIT 1"),
        {"ws": ws_uuid},
    ).fetchone()

    new_version = _bump_version(existing.version if existing else "v1") if existing else "v1"

    db.execute(
        text("""
            INSERT INTO workspace_instructions (workspace_id, content, version, updated_at, updated_by)
            VALUES (:ws, :content, :version, :now, :by)
            ON CONFLICT (workspace_id) DO UPDATE
                SET content    = EXCLUDED.content,
                    version    = EXCLUDED.version,
                    updated_at = EXCLUDED.updated_at,
                    updated_by = EXCLUDED.updated_by
        """),
        {
            "ws": ws_uuid,
            "content": body.content,
            "version": new_version,
            "now": now,
            "by": user_email or user_id,
        },
    )
    db.commit()
    log.info(
        "team_os.instructions_published",
        workspace_id=workspace_id,
        version=new_version,
        updated_by=user_email,
    )

    return _get_instructions(db, workspace_id)


@router.get("/instructions/version", response_model=VersionOut)
def get_instructions_version(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _user_id: str = Depends(get_user_id),
):
    """Lightweight endpoint for CLI staleness check.
    Returns only version + updated_at — no content payload.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    row = db.execute(
        text("""
            SELECT version, updated_at
            FROM workspace_instructions
            WHERE workspace_id = :ws
            LIMIT 1
        """),
        {"ws": ws_uuid},
    ).fetchone()

    if not row:
        return VersionOut(version="v1", updated_at=None)

    return VersionOut(
        version=row.version,
        updated_at=row.updated_at.isoformat() if row.updated_at else None,
    )


@router.get("/instructions/adoption", response_model=list[AdoptionMember])
def get_adoption(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
):
    """Return per-member sync status for the current instructions version.

    For each workspace member:
    - email: from workspace_users
    - tools: distinct AI tools seen in guard_audit_events in the last 30 days
    - last_synced: most recent guard_audit_events.ts for that user
    - version: instructions_version from guard_member_config (null = never synced)
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    rows = db.execute(
        text("""
            SELECT
                wu.email,
                gmc.instructions_version,
                MAX(gae.ts)                                    AS last_synced,
                COALESCE(
                    array_agg(DISTINCT gae.ai_tool)
                        FILTER (WHERE gae.ai_tool IS NOT NULL),
                    ARRAY[]::text[]
                )                                              AS tools
            FROM workspace_users wu
            LEFT JOIN guard_member_config gmc
                   ON gmc.workspace_id = wu.workspace_id
                  AND gmc.clerk_user_id = wu.clerk_user_id
            LEFT JOIN guard_audit_events gae
                   ON gae.workspace_id = wu.workspace_id
                  AND gae.user_email   = wu.email
                  AND gae.ts          >= :cutoff
            WHERE wu.workspace_id = :ws
            GROUP BY wu.email, gmc.instructions_version
            ORDER BY wu.email ASC
        """),
        {"ws": ws_uuid, "cutoff": cutoff},
    ).fetchall()

    return [
        AdoptionMember(
            email=r.email,
            tools=list(r.tools) if r.tools else [],
            last_synced=r.last_synced.isoformat() if r.last_synced else None,
            version=r.instructions_version,
        )
        for r in rows
    ]
