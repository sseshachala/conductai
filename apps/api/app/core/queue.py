"""Shared Redis run queue helpers used by all routers that enqueue runs."""
import redis
from fastapi import HTTPException

from app.core.config import settings

QUEUE_KEY = "marshal:runs:queue"
QUEUE_MAX_DEPTH = 50_000

_ENQUEUE_LUA = """
local depth = redis.call('LLEN', KEYS[1])
if depth >= tonumber(ARGV[2]) then
    return -1
end
return redis.call('RPUSH', KEYS[1], ARGV[1])
"""


def enqueue_run(run_id: str) -> None:
    """Push run_id onto the Redis queue atomically. Raises 503 when queue is at capacity."""
    r = redis.from_url(settings.redis_url, decode_responses=True)
    result = r.eval(_ENQUEUE_LUA, 1, QUEUE_KEY, run_id, QUEUE_MAX_DEPTH)
    if result == -1:
        depth = r.llen(QUEUE_KEY)
        raise HTTPException(status_code=503, detail=f"Run queue at capacity ({depth} pending). Try again shortly.")
