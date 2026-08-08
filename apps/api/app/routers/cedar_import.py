"""Cedar policy import - converts Cedar JSON policies into Guard packs.
Also provides Cedar text export of any Guard pack for readability.

POST /guard/registry/import-cedar        - preview or install a pack from Cedar policies
GET  /guard/registry/packs/{slug}/cedar  - render an installed pack as Cedar text

Runtime evaluation stays on the JSON pack format. Import is one-way.
Export renders the JSON pack in Cedar syntax for readers who prefer it.
See docs/cedar-adapter-spec.md for the full mapping table.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.cedar_adapter import cedar_json_bundle_to_pack, pack_to_cedar_text
from app.modules.guard.models import SkillPack, WorkspaceSkillPack
from app.modules.guard.policy_engine import invalidate_policy_cache


router = APIRouter(prefix="/guard/registry", tags=["cedar-import"])


# ── Schemas ────────────────────────────────────────────────────────────────

class CedarImportRequest(BaseModel):
    format: Literal["cedar_json"] = Field(
        "cedar_json",
        description="Input format. Only cedar_json (Cedar's JSON representation) is supported for MVP. Cedar text grammar is Phase 1.5.",
    )
    policies: list[dict[str, Any]] = Field(
        ...,
        description="List of Cedar policy objects in Cedar JSON representation.",
    )
    pack_slug: str = Field(..., min_length=3, max_length=100)
    pack_name: str = Field(..., min_length=3, max_length=200)
    pack_version: str = Field("1.0.0", min_length=1, max_length=32)
    pack_description: str | None = None
    preview_only: bool = Field(
        True,
        description="When True, return the converted pack without installing. When False, create the SkillPack row and install it in the workspace.",
    )


class RejectionOut(BaseModel):
    index: int
    error: dict[str, Any]


class CedarImportResponse(BaseModel):
    pack_slug: str
    rules_imported: int
    rules_rejected: int
    rejections: list[RejectionOut]
    pack: dict[str, Any] | None
    installed: bool


# ── Endpoint ───────────────────────────────────────────────────────────────

@router.post("/import-cedar", response_model=CedarImportResponse)
def import_cedar(
    body: CedarImportRequest,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.marketplace.install")),
    db: Session = Depends(get_db),
) -> CedarImportResponse:
    """Convert Cedar policies into a Guard pack.

    preview_only=True (default) returns the converted pack without installing.
    preview_only=False creates the SkillPack row and installs it in the workspace.
    """
    if body.format != "cedar_json":
        raise HTTPException(status_code=400, detail=f"Unsupported format: {body.format!r}. Only cedar_json is supported for MVP.")

    if not isinstance(body.policies, list) or not body.policies:
        raise HTTPException(status_code=400, detail="policies must be a non-empty list of Cedar policy objects")

    pack_metadata = {
        "slug": body.pack_slug,
        "name": body.pack_name,
        "version": body.pack_version,
        "tier": "paid",
        "description": body.pack_description or f"Imported from {len(body.policies)} Cedar policies on {datetime.now(timezone.utc).date().isoformat()}.",
    }

    pack = cedar_json_bundle_to_pack(body.policies, pack_metadata)
    rejections = pack.get("_rejections", [])
    rules_imported = len(pack.get("rules", []))
    rules_rejected = len(rejections)

    installed = False
    if not body.preview_only and rules_imported > 0:
        ws_uuid = uuid.UUID(workspace_id)

        existing = db.query(SkillPack).filter(SkillPack.slug == body.pack_slug, SkillPack.version == body.pack_version).first()
        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"SkillPack {body.pack_slug}@{body.pack_version} already exists. Bump pack_version to create a new revision.",
            )

        new_pack = SkillPack(
            slug=body.pack_slug,
            name=body.pack_name,
            version=body.pack_version,
            tier="paid",
            description=pack_metadata["description"],
            rules=pack.get("rules", []),
            published_at=datetime.now(timezone.utc),
        )
        db.add(new_pack)
        db.flush()

        existing_install = db.get(WorkspaceSkillPack, (ws_uuid, body.pack_slug))
        if not existing_install:
            db.add(WorkspaceSkillPack(
                workspace_id=ws_uuid,
                pack_slug=body.pack_slug,
                pinned_version=body.pack_version,
                installed_at=datetime.now(timezone.utc),
            ))

        invalidate_policy_cache(db, ws_uuid)
        db.commit()
        installed = True

    return CedarImportResponse(
        pack_slug=body.pack_slug,
        rules_imported=rules_imported,
        rules_rejected=rules_rejected,
        rejections=[RejectionOut(**r) for r in rejections],
        pack=pack if body.preview_only else None,
        installed=installed,
    )


@router.get("/packs/{slug}/cedar", response_class=PlainTextResponse)
def export_pack_as_cedar(
    slug: str,
    version: str | None = None,
    _: str = Depends(require_permission("platform.marketplace.browse")),
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Render a Guard pack as Cedar text syntax.

    Returns the latest version of the pack unless ?version=X.Y.Z is supplied.
    Runtime evaluation still uses the JSON representation; this endpoint is
    for human readability only.
    """
    query = db.query(SkillPack).filter(SkillPack.slug == slug)
    if version:
        query = query.filter(SkillPack.version == version)
    else:
        query = query.order_by(SkillPack.version.desc())
    pack = query.first()
    if not pack:
        raise HTTPException(status_code=404, detail=f"Pack {slug!r} not found")

    pack_dict = {
        "slug": pack.slug,
        "name": pack.name,
        "version": pack.version,
        "tier": pack.tier,
        "description": pack.description,
        "rules": pack.rules or [],
    }
    return PlainTextResponse(pack_to_cedar_text(pack_dict), media_type="text/plain; charset=utf-8")
