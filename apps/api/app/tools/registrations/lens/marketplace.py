"""Lens tool registrations — marketplace domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _actor_impl,
    _window_start,
    _LIMIT,
    _DECISION,
    _TS_SINCE,
    _TS_UNTIL,
    _RULE_ID,
    _DAYS_WINDOW,
    _TIME_WINDOW,
    _READ_ONLY,
    _READ_ONLY_OPEN_WORLD,
    _LENS_TAGS,
    _ACTOR_TAGS
)

# ── Free-function tool implementations ─────────────────────────────────
def list_installed_packs(ctx):
    """Installed skill packs for this workspace's org. Migrated from
    Executor._tool_list_installed_packs (epic #1655)."""
    from app.core.database import SessionLocal
    from app.modules.guard.models import WorkspaceSkillPack
    from app.modules.guard.routers.spend import _org_ws_subquery
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, ctx.workspace_id)
        rows = (db.query(WorkspaceSkillPack)
                .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
                .order_by(WorkspaceSkillPack.installed_at.desc()).all())
        return [{"pack_slug": r.pack_slug, "pinned_version": r.pinned_version,
                 "installed_by": r.installed_by,
                 "installed_at": r.installed_at.isoformat() if r.installed_at else None}
                for r in rows]
    finally:
        db.close()


def browse_marketplace(ctx, query: str | None = None, limit: int = 30):
    """Available skill packs in the catalog. Migrated from
    Executor._tool_browse_marketplace (epic #1655)."""
    from sqlalchemy import func as sa_func, or_ as sa_or
    from app.core.database import SessionLocal
    from app.modules.guard.models import SkillPack
    db = SessionLocal()
    try:
        q = db.query(SkillPack)
        if query:
            like = f"%{query.lower()}%"
            q = q.filter(sa_or(
                sa_func.lower(SkillPack.slug).like(like),
                sa_func.lower(SkillPack.name).like(like),
                sa_func.lower(SkillPack.description).like(like)))
        rows = q.order_by(SkillPack.slug.asc(), SkillPack.version.desc()).limit(min(limit * 3, 200)).all()
        seen, out = set(), []
        for r in rows:
            if r.slug in seen:
                continue
            seen.add(r.slug)
            rules = r.rules if isinstance(r.rules, list) else []
            out.append({"slug": r.slug, "version": r.version, "name": r.name,
                        "description": r.description, "tier": r.tier,
                        "rules_count": len(rules),
                        "published_at": r.published_at.isoformat() if r.published_at else None})
            if len(out) >= limit:
                break
        return out
    finally:
        db.close()


def get_pack_details(ctx, slug: str):
    """Full rule list for one skill pack (latest version). Migrated from
    Executor._tool_get_pack_details (epic #1655)."""
    from app.core.database import SessionLocal
    from app.modules.guard.models import SkillPack
    db = SessionLocal()
    try:
        r = db.query(SkillPack).filter(SkillPack.slug == slug).order_by(SkillPack.version.desc()).first()
        if not r:
            return {"error": f"Pack '{slug}' not found"}
        rules = r.rules if isinstance(r.rules, list) else []
        return {"slug": r.slug, "version": r.version, "name": r.name,
                "description": r.description, "tier": r.tier,
                "rules_count": len(rules), "rules": rules,
                "published_at": r.published_at.isoformat() if r.published_at else None}
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_installed_packs",
        description="List installed skill packs for this workspace's org.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_installed_packs,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="browse_marketplace",
        description="Available skill packs in the catalog (latest version per slug). Optional query for substring match on slug/name/description.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring search"},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=browse_marketplace,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_pack_details",
        description="One skill pack's latest version with the full rule list.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Pack slug"}},
            "required": ["slug"],
        },
        impl=get_pack_details,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
