"""Compliance Packs — install/uninstall workspace skill packs.

POST   /compliance/packs/{pack_id}/install    — register pack for the workspace
DELETE /compliance/packs/{pack_id}/uninstall  — remove pack registration
GET    /compliance/packs/installed            — list installed pack_ids

Rules live in skill_packs.rules JSONB (versioned, seeded from JSON files).
install_pack only writes a workspace_skill_packs row; compute_policy() resolves
the active ruleset on demand and caches it in guard_policy_cache.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import SkillPack, WorkspaceSkillPack
from app.modules.guard.policy_engine import invalidate_policy_cache

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _latest_pack(db: Session, slug: str) -> SkillPack | None:
    return (
        db.query(SkillPack)
        .filter(SkillPack.slug == slug)
        .order_by(SkillPack.version.desc())
        .first()
    )


# ── Schemas ───────────────────────────────────────────────────────────────────

class PackStatusOut(BaseModel):
    pack_id: str
    guard_rules_installed: int


class InstalledPacksOut(BaseModel):
    installed: list[str]


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/packs/installed", response_model=InstalledPacksOut)
def list_installed_packs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return installed pack slugs (e.g. 'conduct-owasp'). Single identifier
    scheme across the entire surface — slugs only, no legacy translation."""
    ws_uuid = uuid.UUID(workspace_id)
    rows = (
        db.query(WorkspaceSkillPack.pack_slug)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .all()
    )
    return InstalledPacksOut(installed=sorted(r[0] for r in rows))


@router.post("/packs/{pack_id}/install", response_model=PackStatusOut)
def install_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    slug = pack_id
    pack = _latest_pack(db, slug)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found")

    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)

    existing = db.get(WorkspaceSkillPack, (ws_uuid, slug))
    if not existing:
        db.add(WorkspaceSkillPack(
            workspace_id=ws_uuid,
            pack_slug=slug,
            installed_by="compliance:install",
            installed_at=now,
        ))

    invalidate_policy_cache(db, ws_uuid)
    db.commit()

    return PackStatusOut(
        pack_id=pack_id,
        guard_rules_installed=len(pack.rules or []),
    )


@router.delete("/packs/{pack_id}/uninstall", response_model=PackStatusOut)
def uninstall_pack(
    pack_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    slug = pack_id
    ws_uuid = uuid.UUID(workspace_id)

    pack = _latest_pack(db, slug)
    rules_count = len(pack.rules or []) if pack else 0

    deleted = (
        db.query(WorkspaceSkillPack)
        .filter(
            WorkspaceSkillPack.workspace_id == ws_uuid,
            WorkspaceSkillPack.pack_slug == slug,
        )
        .delete(synchronize_session=False)
    )

    if deleted:
        invalidate_policy_cache(db, ws_uuid)

    db.commit()

    return PackStatusOut(pack_id=pack_id, guard_rules_installed=rules_count)
