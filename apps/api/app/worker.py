"""
Runtime worker — polls Redis queue and executes runs.
"""
import time
import redis
import structlog

from app.core.config import settings
from app.core.logging import setup_logging
from app.runtime.executor import execute_run

setup_logging()
log = structlog.get_logger(__name__)

QUEUE_KEY = "marshal:runs:queue"


def main():
    log.info("worker.starting", queue=QUEUE_KEY)
    r = redis.from_url(settings.redis_url, decode_responses=True)

    while True:
        try:
            item = r.blpop(QUEUE_KEY, timeout=5)
            if item is None:
                continue
            _, run_id = item
            log.info("worker.dequeued", run_id=run_id)
            execute_run(run_id)
        except redis.exceptions.ConnectionError:
            log.warning("worker.redis_disconnected", retry_in=3)
            time.sleep(3)
        except Exception:
            log.exception("worker.loop_error")
            time.sleep(1)


if __name__ == "__main__":
    main()
