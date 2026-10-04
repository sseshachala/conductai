"""Durable Guard projection outbox, bounded dispatch, leasing, and recovery."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

import redis
import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.models.workspace import Workspace
from app.modules.guard.models import GuardProjectionIntent, GuardProjectionSummary
from app.modules.guard.observability.metrics import (
    GUARD_PROJECTION_DISPATCH,
    GUARD_PROJECTION_EVENTS,
    GUARD_PROJECTION_OLDEST_AGE,
    GUARD_PROJECTION_OUTCOMES,
    GUARD_PROJECTION_QUEUE_DEPTH,
)
from app.modules.guard.projection_contract import (
    PROJECTION_DEAD_LETTER_KEY,
    PROJECTION_PROCESSING_KEY,
    PROJECTION_QUEUE_KEY,
    ProjectionIntentStatus,
    ProjectionMessage,
    ProjectionSourceKind,
)
from app.modules.guard.projection_policy import (
    audit_event_projection_reason,
    audit_event_source_version,
    normalize_projection_decision,
    projection_expires_at,
    projection_is_expired,
)

log = structlog.get_logger(__name__)
_RECONCILIATION_CURSOR_KEY = "marshal:projections:reconciliation:workspace-cursor"
_TERMINAL = {
    ProjectionIntentStatus.COMPLETED,
    ProjectionIntentStatus.SUPERSEDED,
    ProjectionIntentStatus.EXPIRED,
    ProjectionIntentStatus.MISSING,
}


@dataclass(frozen=True)
class ProjectionClaim:
    """Scalar claim state safe to retain after the claim transaction commits."""

    intent_id: UUID
    workspace_id: UUID
    attempts: int
    max_attempts: int


def _utc(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _summary_window(ts: datetime) -> tuple[datetime, datetime]:
    ts = _utc(ts)
    minutes = settings.guard_projection_allowed_summary_window_minutes
    epoch_minutes = int(ts.timestamp() // 60)
    start_minutes = epoch_minutes - (epoch_minutes % minutes)
    start = datetime.fromtimestamp(start_minutes * 60, tz=timezone.utc)
    return start, start + timedelta(minutes=minutes)


def _bounded_dimension(value: object, limit: int) -> str:
    text = str(value or "unknown").strip().lower()[:limit]
    return text if re.fullmatch(r"[a-z0-9_.:-]+", text) else "other"


def _message(intent: GuardProjectionIntent) -> ProjectionMessage:
    return ProjectionMessage(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        source_kind=ProjectionSourceKind(intent.source_kind),
        source_id=intent.source_id,
        source_version=intent.source_version,
    )


def _new_intent(
    db: Session,
    *,
    workspace_id,
    source_kind: ProjectionSourceKind,
    source_id: str,
    source_version: str,
    now: datetime,
) -> ProjectionMessage:
    intent = GuardProjectionIntent(
        workspace_id=workspace_id,
        source_kind=source_kind.value,
        source_id=source_id,
        source_version=source_version,
        status=ProjectionIntentStatus.PENDING.value,
        attempts=0,
        max_attempts=settings.guard_projection_max_attempts,
        available_at=now,
    )
    db.add(intent)
    db.flush()
    return _message(intent)


def persist_audit_event_projection(
    db: Session,
    event,
    *,
    evaluated_rules: list[dict] | None = None,
    now: datetime | None = None,
) -> ProjectionMessage | None:
    """Persist an event or summary intent in the caller transaction."""
    current = _utc(now or datetime.now(timezone.utc))
    source_ts = _utc(event.ts)
    expires_at = projection_expires_at(
        ProjectionSourceKind.AUDIT_EVENT,
        source_ts,
        settings.guard_projection_retention_days,
    )
    if projection_is_expired(expires_at, current):
        GUARD_PROJECTION_EVENTS.labels(result="expired").inc()
        return None
    reason = audit_event_projection_reason(event.decision, evaluated_rules)
    if reason is not None:
        GUARD_PROJECTION_EVENTS.labels(result="eligible").inc()
        return _new_intent(
            db,
            workspace_id=event.workspace_id,
            source_kind=ProjectionSourceKind.AUDIT_EVENT,
            source_id=str(event.id),
            source_version=audit_event_source_version(event),
            now=current,
        )
    if normalize_projection_decision(event.decision) != "allowed":
        GUARD_PROJECTION_EVENTS.labels(result="skipped").inc()
        return None
    GUARD_PROJECTION_EVENTS.labels(result="skipped").inc()
    GUARD_PROJECTION_EVENTS.labels(result="summarized").inc()
    window_start, window_end = _summary_window(source_ts)
    ai_tool = _bounded_dimension(event.ai_tool, 50)
    tool_call = _bounded_dimension(event.tool_call, 255)
    raw_rule_id = str(event.rule_id or "none")
    rule_id = (
        "none"
        if raw_rule_id == "none"
        else hashlib.sha256(raw_rule_id.encode()).hexdigest()[:16]
    )
    dimension_key = hashlib.sha256(
        json.dumps([ai_tool, tool_call, rule_id], separators=(",", ":")).encode()
    ).hexdigest()
    summary_expiry = projection_expires_at(
        ProjectionSourceKind.AUDIT_SUMMARY,
        window_end,
        settings.guard_projection_retention_days,
    )
    facts = {
        "decision": "allowed",
        "ai_tool": ai_tool,
        "tool_call": tool_call,
        "rule_id": rule_id,
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
    }
    stmt = insert(GuardProjectionSummary).values(
        workspace_id=event.workspace_id,
        window_start=window_start,
        window_end=window_end,
        dimension_key=dimension_key,
        ai_tool=ai_tool,
        tool_call=tool_call,
        rule_id=rule_id,
        event_count=1,
        version=1,
        canonical_facts=facts,
        source_timestamp=window_end,
        expires_at=summary_expiry,
        created_at=current,
        updated_at=current,
    )
    stmt = stmt.on_conflict_do_update(
        constraint="uq_guard_projection_summary_window_dimension",
        set_={
            "event_count": GuardProjectionSummary.event_count + 1,
            "version": GuardProjectionSummary.version + 1,
            "updated_at": current,
        },
    ).returning(GuardProjectionSummary.id, GuardProjectionSummary.version)
    summary_id, version = db.execute(stmt).one()
    return _new_intent(
        db,
        workspace_id=event.workspace_id,
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY,
        source_id=str(summary_id),
        source_version=str(version),
        now=current,
    )


def dispatch_projection_message(
    message: ProjectionMessage, *, redis_client=None
) -> bool:
    try:
        client = redis_client or redis.from_url(
            settings.redis_url, decode_responses=True
        )
        with client.pipeline() as pipe:
            for _ in range(5):
                try:
                    pipe.watch(PROJECTION_QUEUE_KEY, PROJECTION_PROCESSING_KEY)
                    depth = pipe.llen(PROJECTION_QUEUE_KEY) + pipe.llen(
                        PROJECTION_PROCESSING_KEY
                    )
                    if depth >= settings.guard_projection_queue_max_depth:
                        pipe.unwatch()
                        GUARD_PROJECTION_DISPATCH.labels(result="full").inc()
                        return False
                    pipe.multi()
                    pipe.rpush(PROJECTION_QUEUE_KEY, message.to_json())
                    pipe.execute()
                    break
                except redis.WatchError:
                    continue
            else:
                GUARD_PROJECTION_DISPATCH.labels(result="contention").inc()
                return False
    except (redis.RedisError, ConnectionError, OSError, ValueError) as exc:
        GUARD_PROJECTION_DISPATCH.labels(result="unavailable").inc()
        log.warning("guard.projection.redis_unavailable", error_type=type(exc).__name__)
        return False
    GUARD_PROJECTION_DISPATCH.labels(result="enqueued").inc()
    try:
        GUARD_PROJECTION_QUEUE_DEPTH.set(client.llen(PROJECTION_QUEUE_KEY))
    except Exception:  # noqa: BLE001 - metrics must never break dispatch
        log.debug("guard.projection.queue_depth_metric_failed")
    return True


def claim_projection_intent(
    db: Session, message: ProjectionMessage, *, now: datetime | None = None
) -> ProjectionClaim | None:
    current = _utc(now or datetime.now(timezone.utc))
    set_workspace_rls(db, message.workspace_id)
    intent = (
        db.query(GuardProjectionIntent)
        .filter(GuardProjectionIntent.id == message.intent_id)
        .with_for_update(skip_locked=True)
        .first()
    )
    if intent is None:
        return None
    if (
        str(intent.workspace_id) != str(message.workspace_id)
        or intent.source_kind != message.source_kind.value
        or intent.source_id != message.source_id
        or intent.source_version != message.source_version
    ):
        return None
    dispatchable = (
        intent.status in {"pending", "retry"} and intent.available_at <= current
    )
    expired_lease = (
        intent.status == "processing"
        and intent.lease_expires_at is not None
        and intent.lease_expires_at <= current
    )
    if not (dispatchable or expired_lease):
        return None
    intent.status = ProjectionIntentStatus.PROCESSING.value
    intent.attempts += 1
    intent.lease_expires_at = current + timedelta(
        seconds=settings.guard_projection_lease_seconds
    )
    intent.dispatched_at = current
    intent.updated_at = current
    claim = ProjectionClaim(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        attempts=intent.attempts,
        max_attempts=intent.max_attempts,
    )
    db.commit()
    return claim


def _retry_delay(attempts: int) -> int:
    return min(
        settings.guard_projection_retry_max_seconds,
        settings.guard_projection_retry_base_seconds * (2 ** max(attempts - 1, 0)),
    )


def _complete_projection_claim(
    db_factory: Callable[[], Session],
    claim: ProjectionClaim,
    result: ProjectionIntentStatus,
    *,
    now: datetime,
) -> bool:
    with db_factory() as db:
        set_workspace_rls(db, claim.workspace_id)
        intent = (
            db.query(GuardProjectionIntent)
            .filter(GuardProjectionIntent.id == claim.intent_id)
            .with_for_update()
            .first()
        )
        if (
            intent is None
            or intent.status != ProjectionIntentStatus.PROCESSING.value
            or intent.attempts != claim.attempts
        ):
            return False
        intent.status = result.value
        intent.completed_at = now
        intent.lease_expires_at = None
        intent.last_error = None
        intent.updated_at = now
        db.commit()
        return True


def _fail_projection_claim(
    db_factory: Callable[[], Session],
    claim: ProjectionClaim,
    message: ProjectionMessage,
    exc: Exception,
    *,
    redis_client,
    now: datetime,
) -> str:
    with db_factory() as db:
        set_workspace_rls(db, claim.workspace_id)
        intent = (
            db.query(GuardProjectionIntent)
            .filter(GuardProjectionIntent.id == claim.intent_id)
            .with_for_update()
            .first()
        )
        if (
            intent is None
            or intent.status != ProjectionIntentStatus.PROCESSING.value
            or intent.attempts != claim.attempts
        ):
            return "duplicate"
        intent.last_error = f"Projection processing failed ({type(exc).__name__})"[:500]
        intent.lease_expires_at = None
        intent.dispatched_at = None
        intent.updated_at = now
        if claim.attempts >= claim.max_attempts:
            intent.status = ProjectionIntentStatus.DEAD_LETTER.value
            intent.completed_at = now
            outcome = "dead_letter"
        else:
            intent.status = ProjectionIntentStatus.RETRY.value
            intent.available_at = now + timedelta(seconds=_retry_delay(claim.attempts))
            outcome = "retry"
        db.commit()

    if outcome == "dead_letter" and redis_client is not None:
        try:
            pipe = redis_client.pipeline()
            pipe.rpush(PROJECTION_DEAD_LETTER_KEY, message.to_json())
            pipe.ltrim(
                PROJECTION_DEAD_LETTER_KEY,
                -settings.guard_projection_queue_max_depth,
                -1,
            )
            pipe.execute()
        except (redis.RedisError, ConnectionError, OSError):
            log.warning("guard.projection.dead_letter_redis_failed")
    return outcome


def process_projection_message(
    message: ProjectionMessage,
    *,
    db_factory: Callable[[], Session] = SessionLocal,
    redis_client=None,
) -> str:
    with db_factory() as db:
        claim = claim_projection_intent(db, message)
    if claim is None:
        GUARD_PROJECTION_OUTCOMES.labels(outcome="duplicate").inc()
        return "duplicate"

    try:
        # Keep this import contract stable: knowledge owns the projection and
        # accepts only the durable intent id.
        from app.modules.guard.knowledge import process_projection_intent

        result = ProjectionIntentStatus(
            process_projection_intent(str(claim.intent_id))
        )
        if result not in _TERMINAL:
            raise ValueError("projection callback returned non-terminal status")
        completed = _complete_projection_claim(
            db_factory,
            claim,
            result,
            now=datetime.now(timezone.utc),
        )
        outcome = result.value if completed else "duplicate"
        GUARD_PROJECTION_OUTCOMES.labels(outcome=outcome).inc()
        return outcome
    except Exception as exc:  # noqa: BLE001 - callback failures are the retry contract
        outcome = _fail_projection_claim(
            db_factory,
            claim,
            message,
            exc,
            redis_client=redis_client,
            now=datetime.now(timezone.utc),
        )
        GUARD_PROJECTION_OUTCOMES.labels(outcome=outcome).inc()
        return outcome


def mark_projection_dispatched(
    message: ProjectionMessage, *, now: datetime | None = None
) -> None:
    try:
        with SessionLocal() as db:
            set_workspace_rls(db, message.workspace_id)
            intent = db.get(GuardProjectionIntent, message.intent_id)
            if intent and intent.status in {"pending", "retry"}:
                intent.dispatched_at = _utc(now or datetime.now(timezone.utc))
                db.commit()
    except Exception:
        log.exception("guard.projection.dispatch_marker_failed")


def _delivery_timeout_seconds() -> int:
    configured = settings.guard_projection_delivery_timeout_seconds
    if configured is not None:
        return configured
    return max(
        settings.guard_projection_lease_seconds,
        settings.guard_projection_reconciliation_interval_seconds * 2,
    )


def _reserve_reconciliation_messages(
    workspace_id,
    *,
    current: datetime,
    stale_before: datetime,
    limit: int,
) -> tuple[list[ProjectionMessage], datetime | None]:
    """Reserve recoverable rows so concurrent reconcilers cannot hot-dispatch."""
    with SessionLocal() as db:
        set_workspace_rls(db, workspace_id)
        rows = (
            db.query(GuardProjectionIntent)
            .filter(
                sa.or_(
                    sa.and_(
                        GuardProjectionIntent.status.in_(["pending", "retry"]),
                        GuardProjectionIntent.available_at <= current,
                        sa.or_(
                            GuardProjectionIntent.dispatched_at.is_(None),
                            GuardProjectionIntent.dispatched_at <= stale_before,
                        ),
                    ),
                    sa.and_(
                        GuardProjectionIntent.status == "processing",
                        GuardProjectionIntent.lease_expires_at <= current,
                    ),
                )
            )
            .order_by(GuardProjectionIntent.created_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
            .all()
        )
        oldest = rows[0].created_at if rows else None
        messages = [_message(row) for row in rows]
        for row in rows:
            if row.status == ProjectionIntentStatus.PROCESSING.value:
                row.status = ProjectionIntentStatus.RETRY.value
                row.available_at = current
                row.lease_expires_at = None
            row.dispatched_at = current
            row.updated_at = current
        db.commit()
        return messages, oldest


def _release_dispatch_reservation(
    message: ProjectionMessage, *, reserved_at: datetime
) -> None:
    try:
        with SessionLocal() as db:
            set_workspace_rls(db, message.workspace_id)
            intent = (
                db.query(GuardProjectionIntent)
                .filter(GuardProjectionIntent.id == message.intent_id)
                .with_for_update()
                .first()
            )
            if (
                intent is not None
                and intent.status in {"pending", "retry"}
                and intent.dispatched_at is not None
                and _utc(intent.dispatched_at) == reserved_at
            ):
                intent.dispatched_at = None
                db.commit()
    except Exception:
        log.exception("guard.projection.dispatch_reservation_release_failed")


def reconcile_projection_intents(*, redis_client, now: datetime | None = None) -> int:
    """Reserve and re-enqueue a bounded page of recoverable intents."""
    current = _utc(now or datetime.now(timezone.utc))
    batch_size = settings.guard_projection_reconciliation_batch_size
    stale_before = current - timedelta(seconds=_delivery_timeout_seconds())
    cursor = redis_client.get(_RECONCILIATION_CURSOR_KEY)
    with SessionLocal() as db:
        workspace_query = db.query(Workspace.id)
        if cursor:
            workspace_query = workspace_query.filter(Workspace.id > cursor)
        workspace_ids = [
            row.id
            for row in workspace_query.order_by(Workspace.id).limit(batch_size).all()
        ]
    if not workspace_ids:
        redis_client.delete(_RECONCILIATION_CURSOR_KEY)
        GUARD_PROJECTION_OLDEST_AGE.set(0)
        return 0

    messages: list[ProjectionMessage] = []
    oldest = None
    last_workspace_id = None
    for workspace_id in workspace_ids:
        remaining = batch_size - len(messages)
        if remaining <= 0:
            break
        reserved, workspace_oldest = _reserve_reconciliation_messages(
            workspace_id,
            current=current,
            stale_before=stale_before,
            limit=remaining,
        )
        if workspace_oldest is not None and (
            oldest is None or workspace_oldest < oldest
        ):
            oldest = workspace_oldest
        messages.extend(reserved)
        last_workspace_id = workspace_id

    if last_workspace_id is not None:
        redis_client.set(_RECONCILIATION_CURSOR_KEY, str(last_workspace_id))
    GUARD_PROJECTION_OLDEST_AGE.set(
        max(0.0, (current - _utc(oldest)).total_seconds()) if oldest else 0
    )
    dispatched = 0
    for index, message in enumerate(messages):
        if not dispatch_projection_message(message, redis_client=redis_client):
            for reserved_message in messages[index + 1 :]:
                _release_dispatch_reservation(
                    reserved_message,
                    reserved_at=current,
                )
            break
        dispatched += 1
    return dispatched
