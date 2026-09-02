"""Workspace + org name cache for fail-open alerts (#1520).

The alert path must never depend on a live DB lookup — if Guard is falling
open because the database is degraded, a lookup that triggers the same
degradation would silence the alert. This cache is populated best-effort
and returns the raw workspace_id string on any miss or error.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

_TTL_SEC = 300  # 5 minutes


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    workspace_name: str
    org_name: str | None


_cache: dict[str, tuple[float, WorkspaceContext]] = {}


def _now() -> float:
    return time.monotonic()


def resolve_workspace_context(db: Session, workspace_id: str | uuid.UUID) -> WorkspaceContext:
    """Return names for the workspace, caching for 5 minutes.

    On any lookup failure (invalid id, missing row, DB error) returns a
    context with ``workspace_id`` as both id and name so alerts still
    render something useful. Never raises.
    """
    ws_id = str(workspace_id)

    hit = _cache.get(ws_id)
    if hit and _now() - hit[0] < _TTL_SEC:
        return hit[1]

    try:
        row = db.execute(
            text(
                "SELECT w.name AS workspace_name, o.name AS org_name "
                "FROM workspaces w "
                "LEFT JOIN organizations o ON o.id = w.org_id "
                "WHERE w.id = :ws"
            ),
            {"ws": ws_id},
        ).fetchone()
    except Exception as exc:
        log.warning("guard.name_cache.lookup_failed", workspace_id=ws_id, err=str(exc))
        row = None

    if row is None:
        ctx = WorkspaceContext(workspace_id=ws_id, workspace_name=ws_id, org_name=None)
    else:
        ctx = WorkspaceContext(
            workspace_id=ws_id,
            workspace_name=row.workspace_name or ws_id,
            org_name=row.org_name,
        )

    _cache[ws_id] = (_now(), ctx)
    return ctx


def clear_cache() -> None:
    """Test hook — drop all cached entries."""
    _cache.clear()
