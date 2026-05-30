"""
Runtime worker — polls Redis queue and executes runs.

Concurrency: set WORKER_CONCURRENCY=N (default 1) to run N threads
each with their own Redis BLPOP loop.  All threads share the same
queue key so Redis distributes runs across them automatically.

Scale horizontally by running more worker instances in Render
(Dashboard → worker service → Scaling → add instances), or scale
vertically with WORKER_CONCURRENCY.  Example (4 concurrent runs):

    WORKER_CONCURRENCY=4 python -m app.worker

On Render: set WORKER_CONCURRENCY in the worker service's Environment
tab — no code change, just restart the service.

Stale-run reaper: a background daemon thread runs every
STALE_RUN_REAPER_INTERVAL seconds (default 120) and marks any run
that has been in 'running' state with a lock older than
STALE_RUN_THRESHOLD_MINUTES (default 20) as 'failed'.  This recovers
runs whose worker crashed mid-execution.
"""
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import redis
import structlog

from app.core.config import settings
from app.core.logging import setup_logging
from app.runtime.executor import execute_run

setup_logging()
log = structlog.get_logger(__name__)

QUEUE_KEY        = "marshal:runs:queue"
ONLINE_EVAL_KEY  = "marshal:eval:online:queue"
CONCURRENCY      = int(os.environ.get("WORKER_CONCURRENCY", "1"))
JUDGE_SAMPLE_RATE = float(os.environ.get("ONLINE_EVAL_JUDGE_SAMPLE_RATE", "0.20"))

# Reaper configuration — tunable via environment variables.
STALE_RUN_THRESHOLD_MINUTES = int(os.environ.get("STALE_RUN_THRESHOLD_MINUTES", "20"))
STALE_RUN_REAPER_INTERVAL   = int(os.environ.get("STALE_RUN_REAPER_INTERVAL", "120"))  # seconds


# ── stale-run reaper ──────────────────────────────────────────────────────────

def _reap_stale_runs() -> int:
    """
    Query for runs stuck in 'running' state whose worker lock is older than
    STALE_RUN_THRESHOLD_MINUTES and mark them as failed.

    Returns the number of runs reaped.
    """
    from app.core.database import SessionLocal
    from app.models.run import Run, RunEvent

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(minutes=STALE_RUN_THRESHOLD_MINUTES)

    db = SessionLocal()
    try:
        stale = (
            db.query(Run)
            .filter(
                Run.status == "running",
                Run.locked_at.isnot(None),
                Run.locked_at < cutoff,
            )
            .all()
        )
        if not stale:
            return 0

        for run in stale:
            error_msg = (
                "Run timed out — worker did not complete within the allowed window "
                f"({STALE_RUN_THRESHOLD_MINUTES} minutes)"
            )
            run.status = "failed"
            run.completed_at = now
            run.locked_at = None
            run.locked_by = None

            # Write a run_event so the UI event log shows the timeout reason.
            db.add(RunEvent(
                run_id=run.id,
                block_id=None,
                kind="run_failed",
                payload={"status": "failed", "error": error_msg, "reaped": True},
            ))

        db.commit()
        return len(stale)

    except Exception:
        log.exception("reaper.error")
        try:
            db.rollback()
        except Exception:
            pass
        return 0
    finally:
        db.close()


def _reaper_loop() -> None:
    """Daemon thread: sleep, then reap, repeat."""
    log.info(
        "reaper.started",
        threshold_minutes=STALE_RUN_THRESHOLD_MINUTES,
        interval_seconds=STALE_RUN_REAPER_INTERVAL,
    )
    while True:
        time.sleep(STALE_RUN_REAPER_INTERVAL)
        try:
            reaped = _reap_stale_runs()
            if reaped > 0:
                log.warning(
                    "reaper.reaped",
                    count=reaped,
                    threshold_minutes=STALE_RUN_THRESHOLD_MINUTES,
                )
            else:
                log.debug("reaper.cycle", reaped=0)
        except Exception:
            log.exception("reaper.loop_error")


# ── online eval scorer ───────────────────────────────────────────────────────

def _online_eval_loop() -> None:
    """Daemon thread: consume the online eval queue and score each completed run."""
    import random
    r = redis.from_url(settings.redis_url, decode_responses=True)
    log.info("online_eval.started", queue=ONLINE_EVAL_KEY, judge_sample_rate=JUDGE_SAMPLE_RATE)

    while True:
        try:
            item = r.blpop(ONLINE_EVAL_KEY, timeout=30)
            if item is None:
                continue
            _, run_id = item
            use_judge = random.random() < JUDGE_SAMPLE_RATE
            log.debug("online_eval.scoring", run_id=run_id, judge=use_judge)
            try:
                from app.core.database import SessionLocal
                from eval.online_scorer import score_run_online
                with SessionLocal() as db:
                    score_run_online(run_id, db, judge=use_judge)
            except Exception:
                log.exception("online_eval.score_failed", run_id=run_id)
        except redis.exceptions.ConnectionError:
            log.warning("online_eval.redis_disconnected", retry_in=3)
            time.sleep(3)
        except Exception:
            log.exception("online_eval.loop_error")
            time.sleep(1)


# ── queue worker ──────────────────────────────────────────────────────────────

def _loop(thread_id: int) -> None:
    r = redis.from_url(settings.redis_url, decode_responses=True)
    log.info("worker.thread_started", thread_id=thread_id, queue=QUEUE_KEY)

    while True:
        try:
            item = r.blpop(QUEUE_KEY, timeout=5)
            if item is None:
                continue
            _, run_id = item
            log.info("worker.dequeued", run_id=run_id, thread_id=thread_id)
            execute_run(run_id)
        except redis.exceptions.ConnectionError:
            log.warning("worker.redis_disconnected", thread_id=thread_id, retry_in=3)
            time.sleep(3)
        except Exception:
            log.exception("worker.loop_error", thread_id=thread_id)
            time.sleep(1)


def main() -> None:
    log.info("worker.starting", concurrency=CONCURRENCY, queue=QUEUE_KEY)

    # The reaper, watchdog, and online eval scorer run regardless of concurrency.
    reaper = threading.Thread(target=_reaper_loop, daemon=True, name="reaper")
    reaper.start()

    from app.watchdog import watchdog_loop
    watchdog = threading.Thread(target=watchdog_loop, daemon=True, name="watchdog")
    watchdog.start()

    online_eval = threading.Thread(target=_online_eval_loop, daemon=True, name="online-eval")
    online_eval.start()

    if CONCURRENCY == 1:
        _loop(0)
        return

    threads = [
        threading.Thread(target=_loop, args=(i,), daemon=True, name=f"worker-{i}")
        for i in range(CONCURRENCY)
    ]
    for t in threads:
        t.start()

    # Keep main thread alive — if any worker thread dies, log and exit so the
    # process manager (Railway/Docker) restarts the whole worker.
    while True:
        dead = [t for t in threads if not t.is_alive()]
        if dead:
            log.error("worker.thread_died", threads=[t.name for t in dead])
            break  # exit so Render restarts the service
        time.sleep(10)


if __name__ == "__main__":
    main()
