"""Per-identity 30-day activity rollup for GET /workspaces/{id}/agent-identities.

The aggregate scans ~40k guard_audit_events rows for a busy workspace, so it is
cached briefly per workspace; a session count that is 30s stale is harmless.

The rollup is decoration on the identity list, so it runs under a statement
timeout and degrades to "no activity data" instead of stalling the request.
The production canary saw this endpoint hang into a 502 on 2026-11-21/24.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import NamedTuple

import structlog
from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.ttl_cache import TTLCache

log = structlog.get_logger(__name__)

_ACTIVITY_WINDOW_DAYS = 30
_ACTIVITY_TTL_S = 30
_ACTIVITY_TIMEOUT = "5s"
_cache = TTLCache()


class IdentityActivity(NamedTuple):
    session_count: int
    last_activity: datetime | None


def identity_activity(db: Session, workspace_id: str) -> dict[uuid.UUID, IdentityActivity]:
    """agent_identity_id -> (distinct hook sessions, last event ts) over the last 30 days."""
    return _cache.get_or_compute(workspace_id, _ACTIVITY_TTL_S, lambda: _bounded_query(db, workspace_id))


def _bounded_query(db: Session, workspace_id: str) -> dict[uuid.UUID, IdentityActivity]:
    """Run the rollup in a savepoint under a statement timeout; {} when it is cancelled.

    A cancelled rollup is cached like a result, so a slow workspace costs one
    timeout per TTL window rather than one per request.
    """
    if db.get_bind().dialect.name != "postgresql":
        return _query(db, workspace_id)
    previous = db.execute(text("SELECT current_setting('statement_timeout')")).scalar()
    try:
        with db.begin_nested():
            db.execute(text(f"SET LOCAL statement_timeout = '{_ACTIVITY_TIMEOUT}'"))
            result = _query(db, workspace_id)
    except OperationalError as exc:
        # Savepoint rollback already reverted SET LOCAL.
        log.warning("agent_identity.activity_rollup_timeout", workspace_id=workspace_id,
                    error_type=type(exc.orig).__name__)
        return {}
    db.execute(text("SELECT set_config('statement_timeout', :value, true)"), {"value": previous})
    return result


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
