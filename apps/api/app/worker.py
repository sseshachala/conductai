"""
Runtime worker — polls Redis queue and executes runs.

Concurrency: set WORKER_CONCURRENCY=N (default 1) to run N threads
each with their own Redis BLPOP loop.  All threads share the same
queue key so Redis distributes runs across them automatically.

Scale horizontally by running more worker processes; scale vertically
with WORKER_CONCURRENCY.  Example (4 concurrent runs per process):

    WORKER_CONCURRENCY=4 python -m app.worker
"""
import os
import threading
import time

import redis
import structlog

from app.core.config import settings
from app.core.logging import setup_logging
from app.runtime.executor import execute_run

setup_logging()
log = structlog.get_logger(__name__)

QUEUE_KEY   = "marshal:runs:queue"
CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "1"))


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
            break
        time.sleep(10)


if __name__ == "__main__":
    main()
