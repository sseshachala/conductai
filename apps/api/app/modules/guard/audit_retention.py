"""Bounded prefix archival; preserve online receipt/accounting facts."""

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import sqlalchemy as sa
import structlog

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.models.workspace import Workspace
from app.modules.guard.audit_archive import (
    ArchiveIntegrityError, S3ArchiveStore, archive_keys, canonical, digest,
    persist_archive, read_verified_archive, verify_manifest,
)
from app.modules.guard.models import (
    BudgetReservation, GuardAuditArchiveSegment, GuardAuditEvent, GuardAuditRetentionHold,
)

log = structlog.get_logger(__name__)
# Keep every field used by receipts, accounting, reconciliation and attribution.
# Only raw content is removed after its encrypted archive has been verified.
PAYLOAD_FIELDS = ("input_summary", "result_summary", "blast_radius")


def _snapshot(row) -> dict:
    return {column.name: getattr(row, column.name) for column in GuardAuditEvent.__table__.columns}


def _utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def checkpoint_anchor(db, workspace_id, settings_obj=settings, *, summary=None) -> tuple[str, str, int]:
    segments = (db.query(GuardAuditArchiveSegment)
                .filter(GuardAuditArchiveSegment.workspace_id == workspace_id)
                .order_by(GuardAuditArchiveSegment.ordinal).all())
    previous_manifest, previous_entry, ordinal = "", "", 0
    if segments:
        signing, _ = archive_keys(settings_obj)
    for segment in segments:
        manifest = segment.manifest
        verify_manifest(manifest, segment.signature, signing, workspace_id=str(workspace_id),
                        previous_hash=previous_manifest)
        if digest(canonical(manifest)) != segment.manifest_hash or segment.ordinal != ordinal + 1:
            raise ArchiveIntegrityError("Archive checkpoint ordering/hash mismatch")
        if manifest["ordinal"] != segment.ordinal:
            raise ArchiveIntegrityError("Archive checkpoint ordinal mismatch")
        if manifest["first_previous_hash"] is not None:
            if manifest["first_previous_hash"] != previous_entry:
                raise ArchiveIntegrityError("Archive audit boundary is broken")
            previous_entry = manifest["last_entry_hash"]
        count = (db.query(GuardAuditEvent.id).filter(
            GuardAuditEvent.workspace_id == workspace_id,
            GuardAuditEvent.archive_segment_id == segment.id,
            GuardAuditEvent.id.in_([UUID(value) for value in manifest["event_ids"]]),
        ).count())
        if count != manifest["event_count"]:
            raise ArchiveIntegrityError("Archived receipt/accounting references are missing")
        if summary is not None:
            summary["total"] += count
            summary["first_ts"] = summary["first_ts"] or manifest["first_ts"]
            summary["last_ts"] = manifest["last_ts"]
        previous_manifest, ordinal = segment.manifest_hash, segment.ordinal
    return previous_manifest, previous_entry, ordinal


def _eligible_prefix(db, workspace_id, cutoff, limit, *, now, for_update=False):
    query = (db.query(GuardAuditEvent).filter(
        GuardAuditEvent.workspace_id == workspace_id,
        GuardAuditEvent.archive_segment_id.is_(None),
    ).order_by(GuardAuditEvent.ts, GuardAuditEvent.id).limit(limit))
    if for_update:
        query = query.with_for_update()
    rows = query.all()
    holds = db.query(GuardAuditRetentionHold).filter(
        GuardAuditRetentionHold.workspace_id == workspace_id,
        GuardAuditRetentionHold.active.is_(True),
    ).all()
    request_ids = [row.request_id for row in rows if row.request_id]
    open_requests = {row.request_id for row in db.query(BudgetReservation.request_id).filter(
        BudgetReservation.workspace_id == workspace_id,
        BudgetReservation.request_id.in_(request_ids), BudgetReservation.status == "open",
    ).all()} if request_ids else set()
    selected = []
    blocked = None
    for row in rows:
        if _utc(row.ts) >= cutoff:
            break
        if any(_utc(hold.starts_at) <= _utc(row.ts) and
               (hold.ends_at is None or _utc(row.ts) <= _utc(hold.ends_at)) for hold in holds):
            blocked = "legal_hold"
            break
        if row.lifecycle_state not in (None, "finalized", "orphaned", "expired") or row.decision in ("approval_pending", "approval"):
            blocked = "incomplete"
            break
        if row.lease_expires_at is not None and _utc(row.lease_expires_at) > now:
            blocked = "incomplete"
            break
        if row.request_id in open_requests:
            blocked = "open_reservation"
            break
        selected.append(row)
    return selected, blocked


def verify_event_rows(rows, previous_hash="") -> str:
    previous = previous_hash
    for row in rows:
        if not row["entry_hash"]:
            continue
        ts = row["ts"] if isinstance(row["ts"], str) else row["ts"].isoformat()
        expected = digest(f"{ts}|{row['tool_call'] or ''}|{row['decision']}|{previous}".encode())
        if (row["previous_hash"] or "") != previous or row["entry_hash"] != expected:
            raise ArchiveIntegrityError("Audit source chain is broken")
        previous = row["entry_hash"]
    return previous


def _validate_retention_policy(settings_obj):
    days = settings_obj.guard_audit_retention_days
    if days is None:
        raise ValueError("Configure GUARD_AUDIT_RETENTION_DAYS before enabling audit retention")
    if days < settings_obj.guard_projection_retention_days:
        raise ValueError("Audit retention must not be shorter than search projection retention")


def archive_workspace_once(workspace_id, *, session_factory=SessionLocal, settings_obj=settings,
                           store=None, now=None, dry_run=None) -> dict:
    now = _utc(now or datetime.now(timezone.utc))
    workspace_id = UUID(str(workspace_id))
    dry_run = settings_obj.guard_audit_retention_dry_run if dry_run is None else dry_run
    result = {"dry_run": dry_run, "candidates": 0, "archived": 0, "blocked_reason": None}
    days = settings_obj.guard_audit_retention_days
    if days is None:
        return {**result, "blocked_reason": "unconfigured"}
    _validate_retention_policy(settings_obj)
    cutoff = now - timedelta(days=days)
    limit = settings_obj.guard_audit_retention_batch_size
    with session_factory() as db:
        set_workspace_rls(db, workspace_id)
        previous_manifest, previous_entry, ordinal = checkpoint_anchor(db, workspace_id, settings_obj)
        rows, blocked = _eligible_prefix(db, workspace_id, cutoff, limit, now=now)
        snapshot = json.loads(canonical([_snapshot(row) for row in rows]))
    # No database connection is held during upload/read-back/provider failures.
    result.update(candidates=len(snapshot), blocked_reason=blocked)
    if not snapshot:
        return result
    verify_event_rows(snapshot, previous_entry)
    if dry_run:
        return result
    if not settings_obj.guard_audit_retention_enabled:
        return {**result, "blocked_reason": "disabled"}
    store = store or S3ArchiveStore(settings_obj)
    manifest, signature = persist_archive(snapshot, previous_manifest, ordinal + 1, settings_obj, store)
    read_verified_archive(manifest, signature, settings_obj, store, workspace_id=str(workspace_id))
    with session_factory() as db:
        set_workspace_rls(db, workspace_id)
        # Hold creation/release uses the same workspace lock. New holds and
        # source changes during storage I/O must stop compaction, not race it.
        db.execute(sa.text("SET LOCAL lock_timeout = '1s'"))
        db.query(Workspace.id).filter(Workspace.id == workspace_id).with_for_update().one()
        current_manifest, current_entry, current_ordinal = checkpoint_anchor(db, workspace_id, settings_obj)
        if (current_manifest, current_entry, current_ordinal) != (previous_manifest, previous_entry, ordinal):
            return {**result, "blocked_reason": "checkpoint_changed"}
        rows, blocked = _eligible_prefix(db, workspace_id, cutoff, len(snapshot), now=now, for_update=True)
        if canonical([_snapshot(row) for row in rows]) != canonical(snapshot):
            return {**result, "blocked_reason": blocked or "source_changed"}
        segment = GuardAuditArchiveSegment(
            id=uuid4(), workspace_id=workspace_id, ordinal=ordinal + 1, manifest=manifest,
            manifest_hash=digest(canonical(manifest)), signature=signature, archived_at=now,
        )
        db.add(segment)
        db.flush()
        for row in rows:
            for field in PAYLOAD_FIELDS:
                setattr(row, field, None)
            row.archive_segment_id = segment.id
        db.commit()
    result["archived"] = len(snapshot)
    return result


def run_audit_retention_once(*, session_factory=SessionLocal, settings_obj=settings, store=None, now=None) -> dict:
    aggregate = {"workspaces": 0, "candidates": 0, "archived": 0, "errors": 0,
                 "dry_run": settings_obj.guard_audit_retention_dry_run}
    if not settings_obj.guard_audit_retention_enabled:
        return aggregate
    _validate_retention_policy(settings_obj)
    if not aggregate["dry_run"]:
        archive_keys(settings_obj)
        store = store or S3ArchiveStore(settings_obj)
    # Workspace paging bounds each scheduling pass and all owned transactions.
    cursor = None
    while True:
        with session_factory() as db:
            query = db.query(Workspace.id).order_by(Workspace.id)
            if cursor:
                query = query.filter(Workspace.id > cursor)
            ids = [row.id for row in query.limit(100).all()]
        if not ids:
            break
        for workspace_id in ids:
            try:
                result = archive_workspace_once(workspace_id, session_factory=session_factory,
                    settings_obj=settings_obj, store=store, now=now)
                aggregate["workspaces"] += 1
                for name in ("candidates", "archived"):
                    aggregate[name] += result[name]
                from app.modules.guard.observability.metrics import GUARD_AUDIT_RETENTION_EVENTS
                GUARD_AUDIT_RETENTION_EVENTS.labels(outcome=result["blocked_reason"] or "success",
                    dry_run=str(result["dry_run"]).lower()).inc(result["archived"] or result["candidates"])
            except Exception as exc:
                aggregate["errors"] += 1
                # Storage exceptions may contain endpoints/credentials. Log type only.
                log.error("guard.audit_retention.failed", error_type=type(exc).__name__)
        cursor = ids[-1]
    log.info("guard.audit_retention.completed", **aggregate)
    return aggregate


def verify_audit_history(db, workspace_id, *, settings_obj=settings) -> dict:
    workspace_id = UUID(str(workspace_id))
    first_ts = last_ts = broken_at = None
    count = 0
    summary = {"total": 0, "first_ts": None, "last_ts": None}
    try:
        _, previous, _ = checkpoint_anchor(db, workspace_id, settings_obj, summary=summary)
        count, first_ts, last_ts = summary["total"], summary["first_ts"], summary["last_ts"]
        query = db.query(GuardAuditEvent).filter(
            GuardAuditEvent.workspace_id == workspace_id, GuardAuditEvent.archive_segment_id.is_(None),
        ).order_by(GuardAuditEvent.ts, GuardAuditEvent.id).yield_per(100)
        for row in query:
            count += 1
            first_ts = first_ts or row.ts.isoformat()
            last_ts = row.ts.isoformat()
            broken_at = last_ts
            previous = verify_event_rows([_snapshot(row)], previous)
        return {"valid": True, "total": count, "verified_from": first_ts, "broken_at": None,
                "last_event": last_ts}
    except (ArchiveIntegrityError, KeyError, ValueError):
        return {"valid": False, "total": count, "verified_from": first_ts,
                "broken_at": broken_at or "archive_checkpoint", "last_event": last_ts}
