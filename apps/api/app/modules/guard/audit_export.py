"""Audit log export (#2385) — query, serialization and streaming shared by
``GET /guard/events/export`` and the Lens ``export_audit_log`` read tool.

Rows are emitted in chain order ``(ts, id)`` — the same order
``verify_audit_history`` walks — with ``previous_hash``/``entry_hash`` so an
export can be re-verified offline (``conduct audit verify``). The chain hash
is ``sha256(f"{ts.isoformat()}|{tool_call or ''}|{decision}|{previous_hash}")``
(see ``chain_hash_for_insert``); ``ts`` here is emitted via ``isoformat()``
for exactly that reason.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Iterator
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.models import GuardAuditEvent
from app.modules.guard.projection_policy import normalize_decision

AUDIT_EXPORT_MAX_ROWS = 100_000
AUDIT_EXPORT_MAX_DAYS = 366
EXPORT_FORMATS = ("ndjson", "csv")
EXPORT_PERMISSION = "platform.audit_log.view"

# Field order is the export schema. ``ts``/``tool_call``/``decision``/
# ``previous_hash``/``entry_hash`` are the hash inputs/outputs.
SCALAR_FIELDS = (
    "id", "chain_position", "ts", "workspace_id", "ai_tool", "tool_call", "source",
    "decision", "rule_id", "rule_message", "input_summary", "result_summary",
    "user_email", "clerk_user_id", "agent_identity_id", "session_id", "hook_session_id",
    "provider", "model", "route", "execution_status", "duration_ms", "tokens_before",
    "tokens_after", "tokens_saved", "cost_usd_before", "cost_usd_after",
    "conductai_run_id", "conductai_workflow", "conductai_workflow_id", "request_id",
    "lifecycle_state", "accepted_at", "finalized_at", "policy_hash", "goal_id", "goal_name",
    "archive_segment_id", "defense_score",
)
JSON_FIELDS = ("blast_radius", "evaluated_rules", "routing_meta")
HASH_FIELDS = ("previous_hash", "entry_hash")
EXPORT_FIELDS = SCALAR_FIELDS + JSON_FIELDS + HASH_FIELDS
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
_CSV_TEXT_FIELDS = ("input_summary", "result_summary", "rule_message", "user_email", "goal_name")


class ExportRangeError(ValueError):
    """Invalid since/until/format/filters."""


def _utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def parse_bound(value: str | datetime, *, is_until: bool = False) -> datetime:
    """Parse an ISO-8601 bound; naive means UTC; a bare-date ``until`` is inclusive of that day."""
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError as exc:
            raise ExportRangeError(f"invalid ISO-8601 timestamp: {value!r}") from exc
    else:
        dt = value
    dt = _utc(dt)
    if is_until and not (dt.hour or dt.minute or dt.second or dt.microsecond):
        dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def validate_request(since: datetime, until: datetime, fmt: str) -> None:
    if fmt not in EXPORT_FORMATS:
        raise ExportRangeError(f"format must be one of {', '.join(EXPORT_FORMATS)}")
    if since >= until:
        raise ExportRangeError("since must be earlier than until")
    if until - since > timedelta(days=AUDIT_EXPORT_MAX_DAYS):
        raise ExportRangeError(f"range must not exceed {AUDIT_EXPORT_MAX_DAYS} days")


def normalize_decisions(decisions: list[str] | None) -> list[str]:
    out: set[str] = set()
    for raw in decisions or []:
        if raw and raw.strip():
            out.update({raw.strip(), normalize_decision(raw)})
    return sorted(out)


def _filtered(q, workspace_id: UUID, since, until, decisions, tool):
    q = q.filter(GuardAuditEvent.workspace_id == workspace_id,
                 GuardAuditEvent.ts >= since, GuardAuditEvent.ts <= until)
    if decisions:
        q = q.filter(GuardAuditEvent.decision.in_(decisions))
    if tool:
        q = q.filter(GuardAuditEvent.tool_call == tool)
    return q


def count_rows(db: Session, workspace_id: UUID, since, until, decisions, tool) -> int:
    return _filtered(db.query(func.count(GuardAuditEvent.id)), workspace_id,
                     since, until, decisions, tool).scalar() or 0


def edge_hashes(db: Session, workspace_id: UUID, since, until, decisions, tool):
    """(head_hash, tail_hash): entry_hash of the first/last chained row in range."""
    base = _filtered(db.query(GuardAuditEvent.entry_hash), workspace_id, since, until, decisions, tool)
    base = base.filter(GuardAuditEvent.entry_hash.isnot(None))
    head = base.order_by(GuardAuditEvent.ts.asc(), GuardAuditEvent.id.asc()).first()
    tail = base.order_by(GuardAuditEvent.ts.desc(), GuardAuditEvent.id.desc()).first()
    return (head[0] if head else None), (tail[0] if tail else None)


def download_path(since: datetime, until: datetime, fmt: str, decisions=None, tool=None) -> str:
    params = [("since", since.isoformat()), ("until", until.isoformat()), ("format", fmt)]
    params += [("decision", d) for d in (decisions or [])]
    if tool:
        params.append(("tool", tool))
    return "/guard/events/export?" + urlencode(params)


def export_filename(since: datetime, until: datetime, fmt: str) -> str:
    return f"conduct-audit-{since.date().isoformat()}_{until.date().isoformat()}.{fmt}"


def _iso(value):
    return value.isoformat() if value is not None else None


def serialize_event(e: GuardAuditEvent, chain_position: int | None = None) -> dict:
    """One export record. Single serializer for NDJSON and CSV."""
    out = {name: getattr(e, name, None) for name in EXPORT_FIELDS}
    for name in ("id", "workspace_id", "session_id", "request_id", "archive_segment_id"):
        out[name] = str(out[name]) if out[name] is not None else None
    for name in ("ts", "accepted_at", "finalized_at"):
        out[name] = _iso(out[name])
    out["chain_position"] = chain_position
    return out


def ndjson_line(rec: dict) -> str:
    return json.dumps(rec, separators=(",", ":"), default=str) + "\n"


def _csv_cell(name: str, value):
    if value is None:
        return ""
    if name in JSON_FIELDS:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    if name in _CSV_TEXT_FIELDS and isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value  # neutralise spreadsheet formula injection
    return value


def _chain_base(db: Session, workspace_id: UUID, since) -> int:
    return (db.query(func.count(GuardAuditEvent.id))
            .filter(GuardAuditEvent.workspace_id == workspace_id, GuardAuditEvent.ts < since,
                    GuardAuditEvent.entry_hash.isnot(None)).scalar() or 0)


def stream_export(workspace_id: UUID, since, until, decisions, tool, fmt: str,
                  cap: int = AUDIT_EXPORT_MAX_ROWS) -> Iterator[str]:
    """Yield the export body in chunks. Owns its DB session (the request's closes first)."""
    db = SessionLocal()
    try:
        set_workspace_rls(db, workspace_id)
        # chain_position is only meaningful for an unfiltered (contiguous) slice.
        position = None if (decisions or tool) else _chain_base(db, workspace_id, since)
        rows = (_filtered(db.query(GuardAuditEvent), workspace_id, since, until, decisions, tool)
                .order_by(GuardAuditEvent.ts.asc(), GuardAuditEvent.id.asc())
                .limit(cap).yield_per(500))
        buf = io.StringIO()
        writer = csv.writer(buf) if fmt == "csv" else None
        if writer:
            writer.writerow(EXPORT_FIELDS)
        for e in rows:
            pos = None
            if position is not None and e.entry_hash:
                position += 1
                pos = position
            rec = serialize_event(e, pos)
            if writer:
                writer.writerow([_csv_cell(n, rec[n]) for n in EXPORT_FIELDS])
            else:
                buf.write(ndjson_line(rec))
            if buf.tell() >= 65536:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        if buf.tell():
            yield buf.getvalue()
    finally:
        db.close()
