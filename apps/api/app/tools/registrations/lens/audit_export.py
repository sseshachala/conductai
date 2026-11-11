"""Lens read tool ``export_audit_log`` (#2385).

A READ tool, not an ActionSpec: it summarises the range (COUNT + chain
head/tail hashes) and hands back a relative ``download_path`` for
``GET /guard/events/export``. It enforces ``platform.audit_log.view`` itself —
Lens is transport, not auth. The endpoint re-checks on download.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import HTTPException

from app.tools.registrations.lens._shared import _LENS_TAGS, _READ_ONLY, _TS_SINCE, _TS_UNTIL
from app.tools.types import ToolDef


FILTERED_HINT = ("Filtered export: rows are not contiguous. Verify with: conduct audit verify "
                 "--allow-gaps <file>. For auditor evidence, export without filters.")
UNFILTERED_HINT = "conduct audit verify <file>"


def export_audit_log(ctx, since: str, until: str, format: str = "ndjson",
                     decision: str | list[str] | None = None, tool: str | None = None):
    """Summarise an audit export for [since, until] and return its download path."""
    from datetime import datetime, timezone
    from app.core.auth import check_permission
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.modules.guard import audit_export as ax

    fmt = (format or "ndjson").lower()
    try:
        start, end = ax.parse_bound(since), ax.parse_bound(until, is_until=True)
        ax.validate_request(start, end, fmt)
    except ax.ExportRangeError as exc:
        return {"error": str(exc)}
    if isinstance(decision, str):
        decision = [decision]
    decisions = ax.normalize_decisions(decision)

    db = SessionLocal()
    try:
        try:
            check_permission(user_id=getattr(ctx, "clerk_user_id", None), workspace_id=str(ctx.workspace_id),
                             credentials=None, db=db, permission=ax.EXPORT_PERMISSION)
        except HTTPException as exc:
            return {"error": f"forbidden: exporting the audit log requires {ax.EXPORT_PERMISSION}",
                    "status_code": exc.status_code}
        set_workspace_rls(db, ctx.workspace_id)
        ws = _uuid.UUID(str(ctx.workspace_id))
        effective_end = min(end, datetime.now(timezone.utc))
        total = ax.count_rows(db, ws, start, effective_end, decisions, tool)
        head, tail = ax.edge_hashes(db, ws, start, effective_end, decisions, tool)
    finally:
        db.close()
    filtered = bool(decisions or tool)
    return {
        "kind": "audit_export",
        "row_count": min(total, ax.AUDIT_EXPORT_MAX_ROWS),
        "since": start.isoformat(),
        "until": end.isoformat(),
        "format": fmt,
        "capped": total > ax.AUDIT_EXPORT_MAX_ROWS,
        "cap": ax.AUDIT_EXPORT_MAX_ROWS,
        "head_hash": head,
        "tail_hash": tail,
        "download_path": ax.download_path(start, end, fmt, decisions, tool),
        "filtered": filtered,
        "verify_hint": FILTERED_HINT if filtered else UNFILTERED_HINT,
    }


def get_audit_feed(ctx, cursor: str | None = None, since: str | None = None, limit: int | None = None):
    """Next page of audit events after ``cursor`` — the pull feed for SIEM collectors."""
    from app.core.auth import check_permission
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.modules.guard import audit_export as ax
    from app.modules.guard.routers.policies_helpers import _write_audit

    try:
        start = ax.parse_bound(since) if since and not cursor else None
        if cursor:
            ax.decode_cursor(cursor)
    except (ax.ExportRangeError, ValueError) as exc:
        return {"error": str(exc)}

    # A service token (cond_feed_*) IS the grant of platform.audit_log.view for
    # this one tool: its scope was verified by the MCP dispatcher. Anything else
    # (including an unknown scope) must pass the normal permission check.
    service = getattr(ctx, "token_scope", None) == "audit_feed" and getattr(ctx, "collector_id", None)
    actor = f"feed-token:{ctx.collector_id}" if service else getattr(ctx, "clerk_user_id", None)
    db = SessionLocal()
    try:
        if not service:
            try:
                check_permission(user_id=getattr(ctx, "clerk_user_id", None), workspace_id=str(ctx.workspace_id),
                                 credentials=None, db=db, permission=ax.EXPORT_PERMISSION)
            except HTTPException as exc:
                return {"error": f"forbidden: reading the audit feed requires {ax.EXPORT_PERMISSION}",
                        "status_code": exc.status_code}
        set_workspace_rls(db, ctx.workspace_id)
        ws = _uuid.UUID(str(ctx.workspace_id))
        if not cursor:
            # Record when a feed starts; follow-up pages are routine polling.
            _write_audit(db, ws, "audit.feed_start", "audit_feed", "export",
                         actor_id=actor,
                         details=f"since={start.isoformat() if start else 'default'}")
        page = ax.feed_page(db, ws, cursor=cursor, since=start,
                            limit=limit or ax.FEED_DEFAULT_LIMIT)
    finally:
        db.close()
    ax.record_feed_pull(ws, actor, page,
                        service_label=(getattr(ctx, "collector_label", None) or "feed token") if service else None)
    return {"kind": "audit_feed", **page}


def get_audit_feed_status(ctx):
    """Which SIEM collectors are pulling the audit feed, when they last pulled, and their lag."""
    from app.core.auth import check_permission
    from app.core.database import SessionLocal
    from app.modules.guard import audit_export as ax

    db = SessionLocal()
    try:
        try:
            check_permission(user_id=getattr(ctx, "clerk_user_id", None), workspace_id=str(ctx.workspace_id),
                             credentials=None, db=db, permission=ax.EXPORT_PERMISSION)
        except HTTPException as exc:
            return {"error": f"forbidden: feed status requires {ax.EXPORT_PERMISSION}",
                    "status_code": exc.status_code}
        try:
            complete_from = ax.chain_complete_from(db, ctx.workspace_id)
        except Exception:  # informational; never fail the status call
            complete_from = None
    finally:
        db.close()
    return {"kind": "audit_feed_status", **ax.feed_status(str(ctx.workspace_id)),
            "chain_complete_from": complete_from}


TOOLS: list[ToolDef] = [ToolDef(
    name="get_audit_feed",
    description=(
        "Continuous pull feed of Guard audit events for SIEM collectors (Splunk, Sentinel, Falcon "
        "LogScale) via `conduct audit feed`. Returns up to `limit` events (default 500, max 1000) "
        "after `cursor`, oldest first, with hash-chain fields, plus next_cursor and has_more. Pass "
        "next_cursor on the next call; omit it on the first call and optionally set `since` "
        "(default: last 24 hours). Events newer than lag_seconds are held back so none are skipped. "
        "Each page also carries `checkpoint` (the latest signed chain-head checkpoint, or null) and "
        "`audit_keys` (public verification keys) so truncation of the chain tail is detectable. "
        "Needs the platform.audit_log.view permission."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "cursor": {"type": "string", "description": "next_cursor from the previous call"},
            "since": {"type": "string", "description": "ISO-8601 start for the first call (ignored with cursor)"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 500},
        },
        "required": [],
    },
    impl=get_audit_feed,
    permission="platform.audit_log.view",
    annotations=_READ_ONLY,
    tags=_LENS_TAGS,
), ToolDef(
    name="get_audit_feed_status",
    description=(
        "Status of the SIEM audit feed: each collector pulling via `conduct audit feed`, when it last "
        "pulled, how far behind it is (lag_seconds) and whether it is stale (no pull for 15 minutes), plus chain_complete_from (the instant from which the hash chain fully covers the audit log; earlier gateway rows predate chaining). "
        "Call this when the user asks whether their SIEM / Splunk / Sentinel is receiving audit events. "
        "Needs the platform.audit_log.view permission."
    ),
    input_schema={"type": "object", "properties": {}, "required": []},
    impl=get_audit_feed_status,
    permission="platform.audit_log.view",
    annotations=_READ_ONLY,
    tags=_LENS_TAGS,
), ToolDef(
    name="export_audit_log",
    description=(
        "Export the Guard audit log (every allow/warn/block decision with its hash-chain fields) for a "
        "date range. Call this whenever the user asks to export, download, or get a copy of the audit "
        "log or audit trail. Returns a summary (row_count, range, chain head/tail hashes, whether the "
        "100,000-row cap was hit) and a download_path the UI renders as a Download button; the file "
        "itself is not returned. Resolve relative ranges ('last week') to ISO-8601 since/until. "
        "Report row_count, say so when capped is true, and relay verify_hint to the user.Needs the platform.audit_log.view permission."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "since": _TS_SINCE,
            "until": _TS_UNTIL,
            "format": {"type": "string", "enum": ["ndjson", "csv"], "default": "ndjson",
                       "description": "ndjson (verifiable with `conduct audit verify`) or csv"},
            "decision": {"type": "array", "items": {"type": "string"},
                         "description": "Optional decision filter: allow, warn, block"},
            "tool": {"type": "string", "description": "Optional exact tool name filter"},
        },
        "required": ["since", "until"],
    },
    impl=export_audit_log,
    permission="platform.audit_log.view",
    annotations=_READ_ONLY,
    tags=_LENS_TAGS,
)]
