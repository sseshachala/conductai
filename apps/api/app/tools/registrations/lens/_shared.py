"""Shared constants + helpers for the Lens tool registration package.

Every domain submodule imports from here; nothing imports back into a
submodule. This keeps the dependency graph a strict tree (no cycles) and
lets `__init__.py` be the only place that composes the full tool list.

Additions here should be additive — renaming a constant or helper is a
breaking change for every submodule.
"""
from __future__ import annotations

from typing import Any, Callable
from datetime import datetime, timedelta, timezone

from app.tools.types import ToolAnnotations


def _window_start(time_window: str) -> datetime:
    """Resolve a symbolic time window (last_24h / last_7d / mtd) to a UTC
    datetime lower bound. Default: last_24h."""
    now = datetime.now(timezone.utc)
    if time_window == "last_7d":
        return now - timedelta(days=7)
    if time_window == "mtd":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return now - timedelta(hours=24)


def _actor_impl(action_name: str) -> Callable[..., Any]:
    """Build a ctx-accepting impl for one actor-substrate mutating tool.

    The impl runs `require_confirmation()` — the actual mutation only fires
    on `POST /glens/actions/{id}/confirm`.
    """
    def _impl_inner(ctx, **kwargs):
        from app.core.database import SessionLocal
        from app.modules.glens.actor.helpers import require_confirmation
        from app.modules.glens.actor.registry import default_action_registry
        from app.modules.glens.actor.types import ActionCtx

        spec = default_action_registry.get(action_name)
        if spec is None:
            return {"error": f"actor spec not registered: {action_name}"}

        db = SessionLocal()
        try:
            action_ctx = ActionCtx(
                db=db,
                workspace_id=ctx.workspace_id,
                clerk_user_id=getattr(ctx, "clerk_user_id", None),
                user_email=getattr(ctx, "user_email", None),
                session_id=getattr(ctx, "session_id", None),
                agent_identity_id=None,
                surface=getattr(ctx, "surface", "lens") or "lens",
            )
            return require_confirmation(action_ctx, spec, kwargs)
        finally:
            db.close()

    _impl_inner.__name__ = f"actor_impl_{action_name}"
    return _impl_inner


# ── Common JSON Schema shapes ────────────────────────────────────────────────

_LIMIT = {"type": "integer", "description": "Max rows to return", "minimum": 1}
_DECISION = {
    "type": "string",
    "description": "Filter by decision (blocked/allowed/warned/audited). Aliases: block/allow/warn/audit.",
}
_TS_SINCE = {"type": "string", "description": "ISO-8601 lower bound on event timestamp"}
_TS_UNTIL = {"type": "string", "description": "ISO-8601 upper bound on event timestamp"}
_RULE_ID = {"type": "string", "description": "Filter by rule_id"}
_DAYS_WINDOW = {"type": "integer", "minimum": 1, "maximum": 365, "description": "Window in days"}
_TIME_WINDOW = {"type": "string", "description": "Symbolic time window — last_24h, last_7d, mtd"}


# ── Annotation + tag constants ───────────────────────────────────────────────

_READ_ONLY = ToolAnnotations(read_only=True)
_READ_ONLY_OPEN_WORLD = ToolAnnotations(read_only=True, open_world=True)

_LENS_TAGS = ("lens",)
_ACTOR_TAGS = ("lens", "actor")
