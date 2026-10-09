"""Per-identity 30-day activity rollup for GET /workspaces/{id}/agent-identities.

The aggregate scans ~40k guard_audit_events rows for a busy workspace, so it is
cached briefly per workspace; a session count that is 30s stale is harmless.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.ttl_cache import TTLCache

_ACTIVITY_WINDOW_DAYS = 30
_ACTIVITY_TTL_S = 30
_cache = TTLCache()


class IdentityActivity(NamedTuple):
    session_count: int
    last_activity: datetime | None


def identity_activity(db: Session, workspace_id: str) -> dict[uuid.UUID, IdentityActivity]:
    """agent_identity_id -> (distinct hook sessions, last event ts) over the last 30 days."""
    return _cache.get_or_compute(workspace_id, _ACTIVITY_TTL_S, lambda: _query(db, workspace_id))


def _query(db: Session, workspace_id: str) -> dict[uuid.UUID, IdentityActivity]:
    from app.modules.guard.models import GuardAuditEvent as Event

    cutoff = datetime.now(timezone.utc) - timedelta(days=_ACTIVITY_WINDOW_DAYS)
    rows = db.query(
        Event.agent_identity_id,
        func.count(func.distinct(Event.hook_session_id)),
        func.max(Event.ts),
    ).filter(
        Event.workspace_id == uuid.UUID(workspace_id),
        Event.ts >= cutoff,
        Event.agent_identity_id.isnot(None),
        Event.hook_session_id.isnot(None),
        Event.hook_session_id != "",
    ).group_by(Event.agent_identity_id).all()
    return {r[0]: IdentityActivity(r[1], r[2]) for r in rows}
