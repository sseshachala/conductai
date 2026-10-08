"""ConductGuard events — unified activity feed (GET /guard/events/unified)."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import bindparam
from sqlalchemy import text as _sql_text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.core.keyset import before_sql
from app.modules.guard.routers.events_common import _org_ws_subquery

router = APIRouter(prefix="/guard/events", tags=["guard"])


@router.get("/unified")
def list_unified_activity(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    source: str | None = Query(default=None, description="policy|tool"),
    status: str | None = Query(default=None, description="allowed|blocked|warned|audited|info|warning|error"),
    actor: str | None = Query(default=None, description="user_email — only matches policy rows"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before: str | None = Query(default=None, description="Keyset cursor '<iso_ts>|<event_id>' from the last row; wins over offset"),
):
    """One feed, three sources later (policy + tool today, run pending)."""
    org_ws = _org_ws_subquery(db, workspace_id)
    ws_ids = [str(r[0]) for r in org_ws.all()]

    # Compare as uuid (not workspace_id::text) so the (workspace_id, ts) indexes apply.
    where = ["workspace_id IN :ws_ids"]
    params: dict = {"ws_ids": ws_ids}
    if source:
        if source not in ("policy", "tool"):
            raise HTTPException(status_code=422, detail="source must be policy|tool")
        where.append("source = :src")
        params["src"] = source
    if status:
        where.append("status = :st")
        params["st"] = status
    if actor:
        where.append("actor = :ac")
        params["ac"] = actor
    if since:
        where.append("ts >= :since")
        params["since"] = since
    if until:
        where.append("ts <= :until")  # note: caller should end-of-day normalise; TODO
        params["until"] = until
    cursor_sql, cursor_params = before_sql(before, "ts", "event_id")
    if cursor_sql:
        where.append(cursor_sql)
        params.update(cursor_params)
        offset = 0

    sql = (
        "SELECT event_id, source, ts, actor, action, status, reason, message, session_id "
        "FROM unified_activity_v "
        "WHERE " + " AND ".join(where) + " "
        "ORDER BY ts DESC, event_id DESC OFFSET :off LIMIT :lim"
    )
    params["off"] = offset
    params["lim"] = limit

    stmt = _sql_text(sql).bindparams(bindparam("ws_ids", expanding=True))
    rows = db.execute(stmt, params).mappings().all()
    return {
        "items": [
            {
                "event_id":   r["event_id"],
                "source":     r["source"],
                "ts":         r["ts"].isoformat() if r["ts"] else None,
                "actor":      r["actor"],
                "action":     r["action"],
                "status":     r["status"],
                "reason":     r["reason"],
                "message":    r["message"],
                "session_id": r["session_id"],
            }
            for r in rows
        ],
        "limit":  limit,
        "offset": offset,
    }
