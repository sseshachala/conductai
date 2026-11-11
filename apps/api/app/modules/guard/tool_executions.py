"""Join caller-reported tool executions to gateway audit rows (#2169).

The gateway stores ``routing_meta.tool_call_correlation_ids`` ({tool_call_id:
correlation_id}) on the audit row for every response containing tool_calls.
Callers report executions (PostToolUse -> /guard/events/usage) carrying that
correlation_id; surfaces that never see the response header (Claude Code,
Codex) send only ``tool_use_id`` and the API resolves the id here.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models.guard_tool_execution import GuardToolExecution
from app.modules.guard.models import GuardAuditEvent

log = structlog.get_logger(__name__)

CORRELATION_ID_RE = re.compile(r"^[0-9a-f]{16}$")
RESOLVE_WINDOW = timedelta(hours=1)
MAX_CORRELATIONS = 50


def valid_correlation_id(value: str | None) -> str | None:
    return value if isinstance(value, str) and CORRELATION_ID_RE.match(value) else None


def resolve_correlation_id(db: Session, ws_uuid: uuid.UUID, tool_use_id: str | None) -> str | None:
    """Look up the correlation id the gateway assigned to ``tool_use_id`` (recent rows only)."""
    if not tool_use_id or len(tool_use_id) > 128:
        return None
    row = db.execute(
        text(
            "SELECT routing_meta -> 'tool_call_correlation_ids' ->> :tcid AS cid "
            "FROM guard_audit_events "
            "WHERE workspace_id = :ws AND ts >= :since "
            "AND source IN ('gateway', 'proxy') "
            "AND jsonb_exists(routing_meta -> 'tool_call_correlation_ids', :tcid) "
            "ORDER BY ts DESC LIMIT 1"
        ),
        {"ws": str(ws_uuid), "since": datetime.now(timezone.utc) - RESOLVE_WINDOW, "tcid": tool_use_id},
    ).first()
    return valid_correlation_id(row[0]) if row else None


def record_tool_execution(
    db: Session,
    ws_uuid: uuid.UUID,
    *,
    correlation_id: str | None,
    tool_use_id: str | None,
    tool_name: str | None,
    hook_session_id: str | None,
    clerk_user_id: str | None,
    execution_status: str | None,
    duration_ms: int | None,
) -> bool:
    """Upsert one execution outcome. Best-effort: never raises."""
    try:
        source = "reported"
        cid = valid_correlation_id(correlation_id)
        if cid is None:
            cid = resolve_correlation_id(db, ws_uuid, tool_use_id)
            source = "resolved"
        if cid is None:
            return False
        values = dict(
            id=uuid.uuid4(), workspace_id=ws_uuid, correlation_id=cid,
            tool_use_id=(tool_use_id or None) and tool_use_id[:255],
            tool_name=(tool_name or None) and tool_name[:255],
            hook_session_id=hook_session_id, clerk_user_id=clerk_user_id,
            execution_status=(execution_status or None) and execution_status[:20],
            duration_ms=duration_ms, correlation_source=source,
            ts=datetime.now(timezone.utc),
        )
        stmt = pg_insert(GuardToolExecution).values(**values).on_conflict_do_update(
            constraint="uq_guard_tool_executions_ws_corr",
            set_={k: values[k] for k in ("execution_status", "duration_ms", "tool_name", "ts")},
        )
        with db.begin_nested():
            db.execute(stmt)
        return True
    except Exception as exc:  # noqa: BLE001 — accounting must not fail on join metadata
        log.warning("tool_execution_record_failed", error=type(exc).__name__)
        return False


def executions_for_event(db: Session, event: GuardAuditEvent) -> dict:
    """Executions in the event's workspace whose correlation_id is in the row's mapping."""
    mapping = (event.routing_meta or {}).get("tool_call_correlation_ids")
    if not isinstance(mapping, dict) or not mapping:
        return {"correlation_ids": {}, "executions": []}
    by_corr = {
        v: k for k, v in list(mapping.items())[:MAX_CORRELATIONS]
        if isinstance(k, str) and valid_correlation_id(v)
    }
    if not by_corr:
        return {"correlation_ids": {}, "executions": []}
    rows = (
        db.query(GuardToolExecution)
        .filter(
            GuardToolExecution.workspace_id == event.workspace_id,
            GuardToolExecution.correlation_id.in_(list(by_corr)),
        )
        .order_by(GuardToolExecution.ts.asc())
        .all()
    )
    return {
        "correlation_ids": {k: v for v, k in by_corr.items()},
        "executions": [
            {
                "correlation_id": r.correlation_id,
                "tool_call_id": by_corr.get(r.correlation_id),
                "tool_name": r.tool_name,
                "execution_status": r.execution_status,
                "duration_ms": r.duration_ms,
                "correlation_source": r.correlation_source,
                "ts": r.ts.isoformat() if r.ts else None,
            }
            for r in rows
        ],
    }
