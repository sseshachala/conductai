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
from app.models.workspace import Workspace
from app.modules.guard.models import SkillPack, WorkspaceSkillPack
from app.modules.guard.policy_engine import invalidate_policy_cache

router = APIRouter(prefix="/compliance", tags=["compliance"])


def _org_ws_subquery(db: Session, workspace_id: str):
    ws_uuid = uuid.UUID(workspace_id)
    ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
    if ws and ws.org_id:
        return db.query(Workspace.id).filter(Workspace.org_id == ws.org_id)
    if ws and ws.owner_id:
        return db.query(Workspace.id).filter(Workspace.owner_id == ws.owner_id)
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


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


class PackRuleOut(BaseModel):
    id: str
    description: str | None = None
    action: str
    severity: str | None = None
    match_tool: str | None = None
    match_pattern: str | None = None
    match_path_pattern: str | None = None
    message: str | None = None
    recommendation: str | None = None
    frameworks: list[str] = []
    iso_control: str | None = None
    persona_affinity: list[str] = []


class PackDetailOut(BaseModel):
    slug: str
    version: str
    name: str
    description: str | None = None
    tier: str
    rules_count: int
    rules: list[PackRuleOut]
    installed: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/packs/installed", response_model=InstalledPacksOut)
def list_installed_packs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return installed pack slugs (e.g. 'conduct-owasp'). Single identifier
    scheme across the entire surface — slugs only, no legacy translation."""
    org_ws = _org_ws_subquery(db, workspace_id)
    rows = (
        db.query(WorkspaceSkillPack.pack_slug)
        .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
        .distinct()
        .all()
    )
    return InstalledPacksOut(installed=sorted(r[0] for r in rows))


# ── Pack catalog (marketplace metadata) ───────────────────────────────────────

@router.get("/packs/catalog")
def list_pack_catalog():
    """List every pack file with the metadata the marketplace UI needs.

    Reads pack JSONs from disk so adding a new pack is a single-file change:
      1. drop apps/api/app/modules/guard/skill_packs/<slug>.json
      2. add <slug> to scripts/seed_skill_packs.py PACK_SLUGS
      3. done — the card appears in the marketplace automatically

    Each pack can opt in to richer UI by declaring a top-level `ui` block:
      {"ui": {"icon": "🛰️", "subtitle": "...", "tags": ["Demo", "Network"]}}

    Missing UI fields fall back to sensible defaults derived from the pack's
    core metadata (slug, name, description).
    """
    from pathlib import Path
    import json as _json

    skill_packs_dir = Path(__file__).resolve().parent.parent / "modules/guard/skill_packs"
    catalog: list[dict] = []

    for pack_path in sorted(skill_packs_dir.glob("*.json")):
        try:
            pack = _json.loads(pack_path.read_text())
        except Exception:
            continue

        slug = pack.get("slug")
        if not slug:
            continue

        ui = pack.get("ui") or {}
        rules = pack.get("rules") or []

        # Rule surface breakdown for the card badges. Best-effort — counts
        # only what the pack self-declares in enforcement contracts.
        proxy_rules = sum(
            1 for r in rules
            if (r.get("enforcement") or {}).get("proxy") in ("hard", "conditional")
        )
        hook_rules = sum(
            1 for r in rules
            if (r.get("enforcement") or {}).get("hook") in ("hard", "conditional")
        )

        catalog.append({
            "id": slug,
            "name": pack.get("name") or slug,
            "icon": ui.get("icon") or "📦",
            "subtitle": ui.get("subtitle") or (pack.get("description") or "")[:180],
            "description": pack.get("description") or "",
            "tags": ui.get("tags") or [],
            "guardRules": len(rules),
            "proxyRules": proxy_rules,
            "hookRules": hook_rules,
            "version": pack.get("version") or "0.0.0",
            "tier": pack.get("tier") or "standard",
        })

    return {"packs": catalog}


@router.get("/packs/{pack_id}", response_model=PackDetailOut)
def get_pack_detail(
    pack_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Full metadata for a single pack including every rule it ships. Used by
    the marketplace detail page so users see exactly what coverage they get
    before installing."""
    pack = _latest_pack(db, pack_id)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' not found")
    org_ws = _org_ws_subquery(db, workspace_id)
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id.in_(org_ws), WorkspaceSkillPack.pack_slug == pack.slug)
        .first()
    ) is not None
    rules_out = [
        PackRuleOut(
            id=r.get("id") or r.get("rule_id") or "",
            description=r.get("description"),
            action=r.get("action", "block"),
            severity=r.get("severity"),
            match_tool=r.get("match_tool"),
            match_pattern=r.get("match_pattern"),
            match_path_pattern=r.get("match_path_pattern"),
            message=r.get("message"),
            recommendation=r.get("recommendation"),
            frameworks=r.get("frameworks") or [],
            iso_control=r.get("iso_control"),
            persona_affinity=r.get("persona_affinity") or [],
        )
        for r in (pack.rules or [])
    ]
    return PackDetailOut(
        slug=pack.slug,
        version=pack.version,
        name=pack.name,
        description=pack.description,
        tier=pack.tier,
        rules_count=len(rules_out),
        rules=rules_out,
        installed=installed,
    )


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
    if pack_id == "conduct-base":
        raise HTTPException(status_code=400, detail="conduct-base is required and cannot be uninstalled")
    slug = pack_id
    ws_uuid = uuid.UUID(workspace_id)
    org_ws = _org_ws_subquery(db, workspace_id)

    pack = _latest_pack(db, slug)
    rules_count = len(pack.rules or []) if pack else 0

    deleted = (
        db.query(WorkspaceSkillPack)
        .filter(
            WorkspaceSkillPack.workspace_id.in_(org_ws),
            WorkspaceSkillPack.pack_slug == slug,
        )
        .delete(synchronize_session=False)
    )

    if deleted:
        for row in db.query(Workspace.id).filter(Workspace.id.in_(org_ws)).all():
            invalidate_policy_cache(db, row[0])

    db.commit()

    return PackStatusOut(pack_id=pack_id, guard_rules_installed=rules_count)
