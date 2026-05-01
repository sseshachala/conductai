"""
Runtime worker — polls Redis queue and executes runs.
"""
import logging
import time

import redis

from app.core.config import settings
from app.runtime.executor import execute_run

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

QUEUE_KEY = "marshal:runs:queue"


def main():
    log.info("Marshal worker starting — polling %s", QUEUE_KEY)
    r = redis.from_url(settings.redis_url, decode_responses=True)

    while True:
        try:
            # BLPOP blocks up to 5s, returns (key, value) or None on timeout
            item = r.blpop(QUEUE_KEY, timeout=5)
            if item is None:
                continue
            _, run_id = item
            log.info("Dequeued run %s", run_id)
            execute_run(run_id)
        except redis.exceptions.ConnectionError:
            log.warning("Redis connection lost, retrying in 3s…")
            time.sleep(3)
        except Exception:
            log.exception("Worker loop error")
            time.sleep(1)


if __name__ == "__main__":
    main()
