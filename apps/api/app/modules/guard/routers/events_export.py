"""GET /guard/events/export — full-fidelity audit log export (#2385)."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard import audit_export as ax
from app.modules.guard.routers.policies_helpers import _write_audit

router = APIRouter(prefix="/guard/events", tags=["guard"])

_MEDIA = {"ndjson": "application/x-ndjson", "csv": "text/csv"}


@router.get("/export")
def export_events(
    since: datetime = Query(description="ISO-8601 inclusive lower bound"),
    until: datetime = Query(description="ISO-8601 inclusive upper bound"),
    format: Literal["ndjson", "csv"] = Query(default="ndjson"),
    decision: list[str] | None = Query(default=None, description="allow|warn|block (repeatable)"),
    tool: str | None = Query(default=None, description="Exact tool_call name"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _permission: str = Depends(require_permission(ax.EXPORT_PERMISSION)),
):
    """Stream every audit event for the caller's workspace in chain order."""
    since, until = ax.parse_bound(since), ax.parse_bound(until, is_until=True)
    try:
        ax.validate_request(since, until, format)
    except ax.ExportRangeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ws_uuid = UUID(workspace_id)
    decisions = ax.normalize_decisions(decision)
    # Pin the upper bound to "now" so the export audit row written below can
    # never fall inside the range it records.
    effective_until = min(until, datetime.now(timezone.utc))
    total = ax.count_rows(db, ws_uuid, since, effective_until, decisions, tool)
    rows = min(total, ax.AUDIT_EXPORT_MAX_ROWS)
    capped = total > ax.AUDIT_EXPORT_MAX_ROWS

    _write_audit(
        db, ws_uuid, "audit.export", "audit_export", "export", actor_id=user_id,
        details=(f"since={since.isoformat()} until={until.isoformat()} format={format} "
                 f"rows={rows} capped={capped} decision={decisions or '*'} tool={tool or '*'}"),
    )
    headers = {
        "Content-Disposition": f'attachment; filename="{ax.export_filename(since, until, format)}"',
        "X-Conduct-Export-Capped": "true" if capped else "false",
        "X-Conduct-Export-Rows": str(rows),
        "Cache-Control": "no-store",
    }
    body = ax.stream_export(ws_uuid, since, effective_until, decisions, tool, format,
                           cap=ax.AUDIT_EXPORT_MAX_ROWS)
    return StreamingResponse(body, media_type=f"{_MEDIA[format]}; charset=utf-8", headers=headers)
