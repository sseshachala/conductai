"""Session event publisher — foundation for the Lens interactive SSE surface (#1480).

One function. Every state-changing endpoint (actor confirm/cancel/decide, run
worker, approval webhooks) calls `publish_session_event(...)` on success.

Two Redis writes per publish:

1. `XADD stream:session:<id>` (MAXLEN 500, TTL 1h) — durable-ish buffer used
   by the SSE endpoint's `Last-Event-Id` replay on reconnect.
2. `PUBLISH chan:session:<id>` — real-time fan-out to any live subscriber
   (SSE endpoint's generator listens on this channel).

Ordering guarantee: subscribers must replay from the Stream from
`Last-Event-Id` FIRST, THEN attach to pub/sub. The stream id from XADD is
what gets sent to the client as the SSE `id:` field.

Zero endpoints exposed. This module is the substrate; consumers wire it in.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import redis
import structlog

from app.core.config import settings

log = structlog.get_logger(__name__)


STREAM_MAXLEN = 500  # per-session ring buffer size — bounds Redis memory
STREAM_TTL_SECONDS = 3600  # 1h reconnect window


def _stream_key(session_id: str) -> str:
    return f"stream:session:{session_id}"


def _channel_key(session_id: str) -> str:
    return f"chan:session:{session_id}"


def _redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def publish_session_event(
    session_id: str | uuid.UUID,
    event_type: str,
    entity: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    *,
    client: redis.Redis | None = None,
) -> str:
    """Publish an event to a Lens session channel.

    Returns the Redis Stream entry id (used as SSE `id:` field so clients can
    resume via `Last-Event-Id`).

    Args:
        session_id: Lens chat session UUID (from `glens_chat_sessions.id`).
        event_type: dotted string, e.g. `action.confirmed`, `run.block_started`.
            See #1480 for the vocabulary.
        entity: optional `{type, id}` for entity-scoped subscription on the
            client (`useLensEvent(stream, "approval", "<id>", ...)`).
        payload: event-specific data. Kept small — no full run state, no
            LLM history. Consumers can re-fetch by id if they need more.
        client: injectable Redis client for tests.

    Fail-open: publish errors are logged and swallowed. A live SSE stream
    dropping an event is preferable to failing the underlying business
    operation (Confirm succeeded → run enqueued → publish blows up → user
    sees a 500 despite the run running). SSE is a UX enhancement, not a
    consistency boundary.
    """
    sid = str(session_id)
    body = {
        "type": event_type,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    if entity:
        body["entity"] = entity
    if payload:
        body["payload"] = payload

    try:
        # Construct the Redis client inside the try so an unreachable Redis
        # (from_url succeeds but pool init fails, or a mocked-to-raise
        # from_url in tests) still fails open — see docstring.
        r = client or _redis()
        # XADD returns the auto-generated stream id (e.g. "1699999999999-0")
        entry_id = r.xadd(
            _stream_key(sid),
            {"body": json.dumps(body)},
            maxlen=STREAM_MAXLEN,
            approximate=True,  # ~ trim, cheaper and bounded
        )
        # Refresh TTL on the stream key — bounds Redis memory for sessions
        # that go quiet. Subscribers within the last hour still get replay.
        r.expire(_stream_key(sid), STREAM_TTL_SECONDS)

        # Envelope the payload with the stream id so subscribers can send it
        # as SSE `id:` and clients can resume from it.
        fanout = json.dumps({"id": entry_id, **body})
        r.publish(_channel_key(sid), fanout)
        return entry_id
    except Exception as exc:
        # Fail-open — see docstring.
        log.warning(
            "glens.event.publish_failed",
            session_id=sid,
            event_type=event_type,
            error=str(exc),
        )
        return ""
