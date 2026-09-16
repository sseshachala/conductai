"""Lens tool registrations — Gateway Profile v2 domain (#2012).

Read-only surface for the v2 config plane. Mutating counterparts
(create_draft, update_working_copy, publish, rollback) live in
`actor.py` because every mutating ToolDef pairs with an ActionSpec and
those must be grouped together — see the actor.py header for the
two-file convention.

Delegates the queries to the same router functions the HTTP endpoints
call, so the surface can't drift from the API. Bypasses the Depends
resolvers by supplying every argument explicitly — the router
function is just plain Python once you skip FastAPI's DI.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.tools.registrations.lens._shared import _LENS_TAGS, _READ_ONLY
from app.tools.types import ToolDef


def _profile_summary(profile: Any) -> dict[str, Any]:
    """Common projection used by list + get + revisions. Trims heavy
    working_copy JSON out of the list view — Lens can fetch the full
    shape via get_gateway_v2_profile if needed."""
    return {
        "id": str(profile.id),
        "name": profile.name,
        "model_alias": profile.model_alias,
        "revisions": len(profile.revisions),
        "bindings": [
            {
                "environment_id": str(b.environment_id),
                "model_alias": b.model_alias,
                "revision_id": str(b.revision_id),
            }
            for b in profile.bindings
        ],
    }


def list_gateway_v2_profiles(ctx) -> dict[str, Any]:
    """Every v2 profile in the workspace, one row each with binding count."""
    from app.core.database import SessionLocal
    from app.routers.gateway_profiles_v2 import list_profiles as _http_list

    db = SessionLocal()
    try:
        rows = _http_list(
            workspace_id=ctx.workspace_id, db=db,
            _ws=ctx.workspace_id, _="lens",
        )
        return {"count": len(rows), "profiles": [_profile_summary(r) for r in rows]}
    finally:
        db.close()


def get_gateway_v2_profile(ctx, profile_id: str) -> dict[str, Any]:
    """Full shape of one v2 profile — working_copy + bindings + revisions."""
    from app.core.database import SessionLocal
    from app.routers.gateway_profiles_v2 import get_profile as _http_get

    try:
        pid = UUID(profile_id)
    except ValueError:
        return {"error": f"{profile_id!r} is not a valid UUID"}

    db = SessionLocal()
    try:
        try:
            profile = _http_get(
                workspace_id=ctx.workspace_id, profile_id=pid, db=db,
                _ws=ctx.workspace_id, _="lens",
            )
        except Exception as exc:
            return {"error": str(exc)}
        return {
            **_profile_summary(profile),
            "working_copy": profile.working_copy,
            "revisions_detail": [
                {
                    "id": str(r.id),
                    "version": r.version,
                    "published_by": r.published_by,
                    "published_at": r.published_at.isoformat(),
                }
                for r in profile.revisions
            ],
        }
    finally:
        db.close()


def list_gateway_v2_revisions(ctx, profile_id: str) -> dict[str, Any]:
    """Version history for one profile. Snapshot payloads are NOT
    included — those can be large; fetch one via get_gateway_v2_profile
    if the user wants to inspect it."""
    from app.core.database import SessionLocal
    from app.routers.gateway_profiles_v2 import list_revisions as _http_revisions

    try:
        pid = UUID(profile_id)
    except ValueError:
        return {"error": f"{profile_id!r} is not a valid UUID"}

    db = SessionLocal()
    try:
        try:
            revs = _http_revisions(
                workspace_id=ctx.workspace_id, profile_id=pid, db=db,
                _ws=ctx.workspace_id, _="lens",
            )
        except Exception as exc:
            return {"error": str(exc)}
        return {
            "count": len(revs),
            "revisions": [
                {
                    "id": str(r.id),
                    "version": r.version,
                    "published_by": r.published_by,
                    "published_at": r.published_at.isoformat(),
                }
                for r in revs
            ],
        }
    finally:
        db.close()


TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_gateway_v2_profiles",
        description=(
            "List every Gateway Profile v2 in the workspace with binding "
            "and revision counts. Read-only; safe to call any time."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_gateway_v2_profiles,
        permission="platform.credentials.manage",
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_gateway_v2_profile",
        description=(
            "Fetch one Gateway Profile v2 by ID — full working_copy, "
            "current bindings, and revision history."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_id": {"type": "string", "description": "Profile UUID."},
            },
            "required": ["profile_id"],
        },
        impl=get_gateway_v2_profile,
        permission="platform.credentials.manage",
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_gateway_v2_revisions",
        description=(
            "History of published revisions for one Gateway Profile v2. "
            "Returns version, publisher, and timestamp per revision — "
            "snapshot JSON is NOT included (fetch via get_gateway_v2_profile)."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "profile_id": {"type": "string", "description": "Profile UUID."},
            },
            "required": ["profile_id"],
        },
        impl=list_gateway_v2_revisions,
        permission="platform.credentials.manage",
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
