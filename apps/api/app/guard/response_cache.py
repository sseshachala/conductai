"""Redis-backed response cache for idempotent replay of retried requests.

Post-P1-review Finding 3 fix. When a client retries the same X-Request-Id
against `/proxy/*` or `/gateway/v1/*`, we must never forward the LLM call
twice — that would double-bill and could return divergent answers. The
correct response is either:

    1. The cached response body from the original attempt (idempotent replay), or
    2. HTTP 409 Conflict with a receipt id + status hint if:
         - the cache entry is missing (TTL expired or original was streaming), or
         - the original is still in flight (lifecycle_state='accepted')

This module owns (1). The 409 branch lives in the proxy handler.

Design notes:
- gzip-compressed body since LLM responses can be several hundred KB.
- Full response envelope (status, content-type, body) so replay is exact.
- Streaming responses NEVER cache — we cannot safely replay an SSE
  stream from bytes without breaking the client's iterator contract.
- Best-effort: any Redis error is logged and treated as a cache miss.
  A cache outage MUST NOT block real inference.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from typing import Optional

import structlog


log = structlog.get_logger(__name__)


_CACHE_KEY_PREFIX = "guard:audit:response:"


@dataclass
class CachedResponse:
    status_code: int
    content_type: str
    body: bytes


def _redis_client():
    """Lazily import + connect to Redis. Returns None if unavailable so
    a Redis outage degrades to cache-miss rather than a hard error."""
    try:
        import redis
        from app.core.config import settings
        # Best-effort connect. socket_timeout avoids the request path
        # hanging on Redis stalls; 200ms is generous vs LLM latency.
        return redis.from_url(
            settings.redis_url,
            socket_connect_timeout=0.2,
            socket_timeout=0.2,
        )
    except Exception as e:
        log.warning("guard.response_cache.redis_unavailable", err=str(e))
        return None


def cache_key(request_id: str) -> str:
    return f"{_CACHE_KEY_PREFIX}{request_id}"


def store(
    request_id: str,
    status_code: int,
    content_type: str,
    body: bytes,
    *,
    ttl_seconds: int,
) -> bool:
    """Store a completed response for later idempotent replay.

    Returns True on success, False on any Redis error. Callers should
    log the failure but never re-raise — a cache miss on subsequent
    retry just means we serve 409 instead of the cached body, which
    still preserves the "never forward twice" invariant.

    NEVER call this for streaming responses; the body isn't a
    complete envelope and replay would be incorrect.
    """
    r = _redis_client()
    if r is None:
        return False
    try:
        envelope = {
            "status_code": status_code,
            "content_type": content_type,
            "body_b64": gzip.compress(body).hex(),
        }
        r.set(
            cache_key(request_id),
            json.dumps(envelope),
            ex=ttl_seconds,
        )
        return True
    except Exception as e:
        log.warning("guard.response_cache.store_failed", err=str(e))
        return False


def fetch(request_id: str) -> Optional[CachedResponse]:
    """Look up a cached response for a request_id. Returns None on miss."""
    r = _redis_client()
    if r is None:
        return None
    try:
        raw = r.get(cache_key(request_id))
        if not raw:
            return None
        envelope = json.loads(raw)
        return CachedResponse(
            status_code=int(envelope["status_code"]),
            content_type=str(envelope["content_type"]),
            body=gzip.decompress(bytes.fromhex(envelope["body_b64"])),
        )
    except Exception as e:
        log.warning("guard.response_cache.fetch_failed", err=str(e))
        return None
