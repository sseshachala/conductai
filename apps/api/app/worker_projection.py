"""Guard projection-queue consumer, reconciliation and retention loops (split from worker.py).

Pure functions/loops started as daemon threads by ``app.worker.main``; this
module does no work at import time. ``app.worker`` re-exports every name here.
"""
import threading
import time
import redis
import structlog
from app.core.config import settings

log = structlog.get_logger("app.worker")


# -- projection queue worker ---------------------------------------------------

def _projection_backlog_depth(client) -> int:
    from app.modules.guard.projection_contract import (
        PROJECTION_PROCESSING_KEY,
        PROJECTION_QUEUE_KEY,
    )

    return int(client.llen(PROJECTION_QUEUE_KEY)) + int(
        client.llen(PROJECTION_PROCESSING_KEY)
    )


def _projection_loop(thread_id: int) -> None:
    from app.modules.guard.observability.metrics import GUARD_PROJECTION_QUEUE_DEPTH
    from app.modules.guard.projection_contract import (
        PROJECTION_PROCESSING_KEY,
        PROJECTION_PROCESSING_TIMES_KEY,
        PROJECTION_QUEUE_KEY,
        ProjectionMessage,
    )
    from app.modules.guard.projection_queue import (
        process_projection_message,
        projection_redis_client,
    )

    client = projection_redis_client(blocking=True)
    log.info("projection_worker.thread_started", thread_id=thread_id, queue=PROJECTION_QUEUE_KEY)
    while True:
        if settings.guard_projection_paused:
            time.sleep(1)
            continue
        raw = None
        try:
            raw = client.blmove(PROJECTION_QUEUE_KEY, PROJECTION_PROCESSING_KEY, 5, "LEFT", "RIGHT")
            if not raw:
                continue
            client.hset(PROJECTION_PROCESSING_TIMES_KEY, raw, time.time())
            message = ProjectionMessage.from_json(raw)
            process_projection_message(message, redis_client=client)
        except redis.exceptions.ConnectionError:
            log.warning("projection_worker.redis_disconnected", thread_id=thread_id)
            time.sleep(3)
        except Exception:
            log.exception("projection_worker.loop_error", thread_id=thread_id)
            time.sleep(1)
        finally:
            if raw is not None:
                try:
                    client.lrem(PROJECTION_PROCESSING_KEY, 1, raw)
                    client.hdel(PROJECTION_PROCESSING_TIMES_KEY, raw)
                except Exception:  # noqa: BLE001 - worker must survive cleanup failure
                    log.warning("projection_worker.cleanup_failed", thread_id=thread_id)
            try:
                GUARD_PROJECTION_QUEUE_DEPTH.set(_projection_backlog_depth(client))
            except Exception:  # noqa: BLE001 - metrics must not break processing
                log.debug("projection_worker.queue_depth_metric_failed", thread_id=thread_id)


def _reconcile_projection_processing_entries(client, *, now: float | None = None) -> int:
    from app.modules.guard.projection_contract import (
        PROJECTION_PROCESSING_KEY,
        PROJECTION_PROCESSING_TIMES_KEY,
        PROJECTION_QUEUE_KEY,
    )

    current = time.time() if now is None else now
    cutoff = current - settings.guard_projection_lease_seconds
    timestamps = client.hgetall(PROJECTION_PROCESSING_TIMES_KEY)
    recovered = 0
    # The list is authoritative for capacity. Inspect every entry, including
    # the BLMOVE-before-HSET crash window where no timestamp exists.
    for raw in client.lrange(PROJECTION_PROCESSING_KEY, 0, -1):
        started = timestamps.get(raw)
        if started is None:
            # A live worker may still be between BLMOVE and HSET. Adopt the
            # entry for one lease window instead of immediately duplicating it.
            client.hset(PROJECTION_PROCESSING_TIMES_KEY, raw, current)
            timestamps[raw] = str(current)
            continue
        try:
            stale = float(started) <= cutoff
        except (TypeError, ValueError):
            stale = True
        if not stale:
            continue
        removed = client.lrem(PROJECTION_PROCESSING_KEY, 0, raw)
        client.hdel(PROJECTION_PROCESSING_TIMES_KEY, raw)
        if removed and client.lpos(PROJECTION_QUEUE_KEY, raw) is None:
            client.rpush(PROJECTION_QUEUE_KEY, raw)
        if removed:
            recovered += 1
    # Hash entries without a corresponding processing-list item are harmless
    # but must be removed so monitoring and future recovery converge.
    processing = set(client.lrange(PROJECTION_PROCESSING_KEY, 0, -1))
    for raw in timestamps:
        if raw not in processing:
            client.hdel(PROJECTION_PROCESSING_TIMES_KEY, raw)
    return recovered


def _projection_reconciliation_loop() -> None:
    from app.modules.guard.observability.metrics import GUARD_PROJECTION_QUEUE_DEPTH
    from app.modules.guard.projection_queue import (
        projection_redis_client,
        reconcile_projection_intents,
    )

    client = projection_redis_client()
    interval = settings.guard_projection_reconciliation_interval_seconds
    log.info("projection_worker.reconciliation_started", interval_seconds=interval)
    while True:
        if not settings.guard_projection_paused:
            try:
                recovered = _reconcile_projection_processing_entries(client)
                dispatched = reconcile_projection_intents(redis_client=client)
                # The reconciler updates oldest-pending age from its bounded DB
                # pass. Refresh depth here so both backlog gauges move during
                # idle and recovery cycles, not only on enqueue.
                GUARD_PROJECTION_QUEUE_DEPTH.set(_projection_backlog_depth(client))
                log.debug(
                    "projection_worker.reconciliation_cycle",
                    recovered=recovered,
                    dispatched=dispatched,
                )
            except Exception:
                log.exception("projection_worker.reconciliation_error")
        time.sleep(interval)


# -- projection retention -----------------------------------------------------

def _record_projection_retention_result(result: dict[str, bool | int]) -> None:
    from app.modules.guard.observability.metrics import (
        GUARD_PROJECTION_RETENTION_INTENTS_DELETED,
        GUARD_PROJECTION_RETENTION_INTENTS_EXPIRED,
        GUARD_PROJECTION_RETENTION_KNOWLEDGE_BACKFILLED,
        GUARD_PROJECTION_RETENTION_KNOWLEDGE_DELETED,
        GUARD_PROJECTION_RETENTION_ORPHANS_DELETED,
        GUARD_PROJECTION_RETENTION_RUNS,
        GUARD_PROJECTION_RETENTION_SUMMARIES_DELETED,
    )

    dry_run = str(bool(result.get("dry_run", False))).lower()
    GUARD_PROJECTION_RETENTION_RUNS.labels(
        outcome="success",
        dry_run=dry_run,
        more_work=str(bool(result.get("more_work", False))).lower(),
    ).inc()
    GUARD_PROJECTION_RETENTION_KNOWLEDGE_BACKFILLED.labels(dry_run=dry_run).inc(
        int(result.get('knowledge_backfilled', 0))
    )
    GUARD_PROJECTION_RETENTION_ORPHANS_DELETED.labels(dry_run=dry_run).inc(
        int(result.get('knowledge_orphans_deleted', 0))
    )
    GUARD_PROJECTION_RETENTION_KNOWLEDGE_DELETED.labels(dry_run=dry_run).inc(
        int(result.get("knowledge_deleted", 0))
    )
    GUARD_PROJECTION_RETENTION_INTENTS_EXPIRED.labels(dry_run=dry_run).inc(
        int(result.get("intents_expired", 0))
    )
    GUARD_PROJECTION_RETENTION_INTENTS_DELETED.labels(dry_run=dry_run).inc(
        int(result.get("intents_deleted", 0))
    )
    GUARD_PROJECTION_RETENTION_SUMMARIES_DELETED.labels(dry_run=dry_run).inc(
        int(result.get("summaries_deleted", 0))
    )


def _projection_retention_loop() -> None:
    """Independent daemon that never occupies run or projection slots."""
    from app.core.database import SessionLocal
    from app.modules.guard.observability.metrics import GUARD_PROJECTION_RETENTION_RUNS
    from app.modules.guard.projection_retention import run_projection_retention_once

    interval = settings.guard_projection_retention_interval_seconds
    dry_run = settings.guard_projection_retention_dry_run
    log.info(
        "projection_retention.started",
        dry_run=dry_run,
        interval_seconds=interval,
    )
    while True:
        try:
            run_projection_retention_once(
                session_factory=SessionLocal,
                dry_run=dry_run,
                on_result=_record_projection_retention_result,
            )
        except Exception:
            GUARD_PROJECTION_RETENTION_RUNS.labels(
                outcome="error",
                dry_run=str(bool(dry_run)).lower(),
                more_work="unknown",
            ).inc()
            # Retention must never take down queue or workflow processing.
            log.exception("projection_retention.cycle_error", dry_run=dry_run)
        time.sleep(interval)


def _audit_retention_loop() -> None:
    from app.modules.guard.audit_retention import run_audit_retention_once
    from app.modules.guard.observability.metrics import (
        GUARD_AUDIT_RETENTION_RUNS, GUARD_AUDIT_RETENTION_LAST_SUCCESS,
    )
    while True:
        mode = str(settings.guard_audit_retention_dry_run).lower()
        try:
            result = run_audit_retention_once()
            outcome = "error" if result["errors"] else "success"
            GUARD_AUDIT_RETENTION_RUNS.labels(outcome=outcome, dry_run=mode).inc()
            if not result["errors"]:
                GUARD_AUDIT_RETENTION_LAST_SUCCESS.set(time.time())
        except Exception as exc:
            GUARD_AUDIT_RETENTION_RUNS.labels(outcome="error", dry_run=mode).inc()
            log.error("audit_retention.cycle_error", error_type=type(exc).__name__)
        time.sleep(settings.guard_audit_retention_interval_seconds)


def _start_audit_retention() -> threading.Thread | None:
    if not settings.guard_audit_retention_enabled:
        return None
    thread = threading.Thread(target=_audit_retention_loop, daemon=True, name="audit-retention")
    thread.start()
    return thread


def _start_projection_retention() -> threading.Thread | None:
    if not settings.guard_projection_retention_cleanup_enabled:
        log.info(
            "projection_retention.disabled",
            dry_run=settings.guard_projection_retention_dry_run,
        )
        return None
    thread = threading.Thread(
        target=_projection_retention_loop,
        daemon=True,
        name="projection-retention",
    )
    thread.start()
    return thread
