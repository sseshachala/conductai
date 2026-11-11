"""Audit log export (#2385) — query, serialization and streaming shared by
``GET /guard/events/export`` and the Lens ``export_audit_log`` read tool.

Rows are emitted in chain order ``(ts, id)`` — the same order
``verify_audit_history`` walks — with ``previous_hash``/``entry_hash``,
``hash_version`` and every hashed column so an export can be re-verified
offline (``conduct audit verify``). v2 rows hash the full record, v1 rows the
legacy four fields (see ``app/modules/guard/audit_chain.py``); ``ts`` is emitted
via ``isoformat()`` because the v1 hash covers that exact string.
"""
from __future__ import annotations

import base64
import csv
import io
import json
from datetime import datetime, timedelta, timezone
from typing import Iterator
from urllib.parse import urlencode
from uuid import UUID

from sqlalchemy import and_, func, or_
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
    # Remaining hashed columns (audit chain v2): an export must carry every
    # field the hash covers so ``conduct audit verify`` works offline.
    "tool_use_id", "os_info", "hostname", "share_token_hash", "lease_expires_at",
    "hash_version", "usage_source", "usage_status",
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
    for name in ("ts", "accepted_at", "finalized_at", "lease_expires_at"):
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
        emitted = 0
        for e in rows:
            emitted += 1
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
        # Signed chain-head checkpoint trailer (#2524 item 2): only for an
        # unfiltered, uncapped NDJSON export, where the rows are a contiguous
        # slice and the checkpoint head is guaranteed to be inside the range.
        if fmt == "ndjson" and not (decisions or tool) and emitted < cap:
            bundle = _checkpoint_bundle(db, workspace_id, until)
            if bundle:
                buf.write(ndjson_line({"kind": CHECKPOINT_TRAILER_KIND, **bundle}))
        if buf.tell():
            yield buf.getvalue()
    finally:
        db.close()


CHECKPOINT_TRAILER_KIND = "audit_checkpoint"


def _checkpoint_bundle(db: Session, workspace_id: UUID, until) -> dict | None:
    """Latest checkpoint taken at or before ``until`` plus the public keys. Never raises."""
    from app.modules.guard.audit_signing import bundle_for
    try:
        return bundle_for(db, workspace_id, until=until)
    except Exception:  # an export must not fail because checkpoints are unavailable
        db.rollback()
        return None


# ── Continuous feed (SIEM pull) ────────────────────────────────────────────
# Pages through events in chain order with an opaque (ts, id) cursor. Rows
# newer than FEED_LAG are held back: ts is assigned before the per-workspace
# chain lock, so a slower transaction can commit a slightly older ts after a
# faster one. Waiting out the lag keeps the cursor from skipping it.
FEED_LAG = timedelta(seconds=60)
FEED_DEFAULT_LIMIT = 500
FEED_MAX_LIMIT = 1000
FEED_DEFAULT_LOOKBACK = timedelta(hours=24)
_CURSOR_FLOOR_ID = UUID(int=0)


def encode_cursor(ts: datetime, event_id: UUID) -> str:
    raw = json.dumps({"ts": _utc(ts).isoformat(), "id": str(event_id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()))
        return _utc(datetime.fromisoformat(data["ts"])), UUID(data["id"])
    except Exception as exc:
        raise ExportRangeError("invalid cursor") from exc


def feed_page(db: Session, workspace_id: UUID, *, cursor: str | None = None,
              since: datetime | None = None, limit: int = FEED_DEFAULT_LIMIT,
              now: datetime | None = None) -> dict:
    """One page of events after ``cursor`` (or from ``since``), oldest first."""
    limit = max(1, min(int(limit), FEED_MAX_LIMIT))
    now = _utc(now or datetime.now(timezone.utc))
    if cursor:
        after_ts, after_id = decode_cursor(cursor)
    else:
        after_ts = _utc(since) if since else now - FEED_DEFAULT_LOOKBACK
        after_id = _CURSOR_FLOOR_ID
    horizon = now - FEED_LAG
    rows = (db.query(GuardAuditEvent)
            .filter(GuardAuditEvent.workspace_id == workspace_id,
                    GuardAuditEvent.ts <= horizon,
                    or_(GuardAuditEvent.ts > after_ts,
                        and_(GuardAuditEvent.ts == after_ts, GuardAuditEvent.id > after_id)))
            .order_by(GuardAuditEvent.ts.asc(), GuardAuditEvent.id.asc())
            .limit(limit + 1)
            .all())
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].ts, rows[-1].id) if rows else encode_cursor(after_ts, after_id)
    page = {
        "events": [serialize_event(e) for e in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
        "lag_seconds": int(FEED_LAG.total_seconds()),
    }
    # Latest signed chain-head checkpoint + public keys (#2524 item 2); null until one exists.
    bundle = _checkpoint_bundle(db, workspace_id, None)
    page["checkpoint"] = bundle["checkpoint"] if bundle else None
    page["audit_keys"] = bundle["keys"] if bundle else {}
    return page


# ── Feed status (last pull per collector) ────────────────────────────────────
# Each feed page updates one Redis hash field per collector (the calling user),
# so the Audit page can show whether a SIEM is still pulling and how far behind
# it is without writing an audit event on every poll. Losing Redis only blanks
# the status until the next pull.

FEED_STALE_AFTER = timedelta(minutes=15)
FEED_STATUS_TTL = timedelta(days=30)


def _feed_status_key(workspace_id) -> str:
    return f"audit_feed:status:{workspace_id}"


def _status_redis():
    import redis

    from app.core.config import settings
    return redis.from_url(settings.redis_url, decode_responses=True)


def record_feed_pull(workspace_id, actor: str | None, page: dict, *,
                     now: datetime | None = None, client=None) -> None:
    """Remember this collector's last pull. Never raises."""
    try:
        cursor_ts, _ = decode_cursor(page["next_cursor"])
        now = _utc(now or datetime.now(timezone.utc))
        r = client or _status_redis()
        key = _feed_status_key(workspace_id)
        r.hset(key, actor or "unknown", json.dumps({
            "last_pull_at": now.isoformat(),
            "cursor_ts": cursor_ts.isoformat(),
            "last_page_events": len(page.get("events") or []),
        }))
        r.expire(key, int(FEED_STATUS_TTL.total_seconds()))
    except Exception:
        pass


def feed_status(workspace_id, *, now: datetime | None = None, client=None) -> dict:
    """Collectors that pulled in the last 30 days, most recent first."""
    now = _utc(now or datetime.now(timezone.utc))
    try:
        raw = (client or _status_redis()).hgetall(_feed_status_key(workspace_id)) or {}
    except Exception:
        return {"available": False, "collectors": [],
                "stale_after_seconds": int(FEED_STALE_AFTER.total_seconds())}
    collectors = []
    for actor, value in raw.items():
        try:
            data = json.loads(value)
            last = _utc(datetime.fromisoformat(data["last_pull_at"]))
            cursor_ts = _utc(datetime.fromisoformat(data["cursor_ts"]))
        except Exception:
            continue
        collectors.append({
            "actor_id": actor,
            "last_pull_at": last.isoformat(),
            "cursor_ts": cursor_ts.isoformat(),
            "lag_seconds": max(0, int((now - cursor_ts).total_seconds())),
            "last_page_events": int(data.get("last_page_events") or 0),
            "stale": now - last > FEED_STALE_AFTER,
        })
    collectors.sort(key=lambda c: c["last_pull_at"], reverse=True)
    return {"available": True, "collectors": collectors,
            "stale_after_seconds": int(FEED_STALE_AFTER.total_seconds())}
