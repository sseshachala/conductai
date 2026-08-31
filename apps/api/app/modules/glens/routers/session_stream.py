"""SSE endpoint for the Lens session event stream — PR 2 of #1480.

    GET /glens/sessions/{session_id}/stream

Long-lived Server-Sent Events connection scoped to one Lens chat session.
Subscribes to Redis pub/sub `chan:session:<id>` for real-time fan-out.
If the client sends a `Last-Event-Id` header, first replays events from
the Redis Stream `stream:session:<id>` starting AFTER that id, then
attaches to pub/sub.

Ordering guarantee: subscribe → replay → forward pub/sub. Subscribe
first so any event published during the replay phase is queued on
pub/sub, not lost.

Producers are wired in later PRs; this endpoint only READS. Publisher
lives in `apps/api/app/modules/glens/events.py` (PR 1).
"""
from __future__ import annotations

import asyncio
import json

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import get_db

from ..events import _channel_key, _stream_key
from ._helpers import _get_session, _parse_workspace_id

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


# Send an SSE comment every N seconds during idle so intermediary proxies
# (nginx, cloudflare) don't drop the connection as stale.
IDLE_KEEPALIVE_SECONDS = 30
# Short pub/sub poll timeout — lets us check request.is_disconnected() and
# emit keepalives without holding a blocking call for minutes.
PUBSUB_POLL_SECONDS = 5


def _sse_frame(entry_id: str, data: str) -> str:
    """Format one SSE frame with the entry id as the `id:` line so clients
    can resume via `Last-Event-Id` after reconnect."""
    if entry_id:
        return f"id: {entry_id}\ndata: {data}\n\n"
    return f"data: {data}\n\n"


async def _stream_events(
    session_id: str,
    last_event_id: str | None,
    is_disconnected,
):
    """Async generator that drives the SSE body for one Lens session.

    Extracted from the endpoint so it can be unit-tested against a real
    Redis without going through httpx / ASGITransport (which buffers
    streaming responses — see PR 6 for the incident).

    Ordering: subscribe FIRST so events published during replay queue on
    pub/sub — otherwise a race can drop events landing between the
    XREAD and the SUBSCRIBE.

    `is_disconnected` is a zero-arg awaitable returning bool — the
    endpoint passes `request.is_disconnected` from FastAPI's Request;
    tests pass a stub.
    """
    stream_key = _stream_key(session_id)
    channel_key = _channel_key(session_id)

    r = aioredis.from_url(settings.redis_url, decode_responses=True)
    pubsub = r.pubsub()
    try:
        await pubsub.subscribe(channel_key)

        if last_event_id:
            try:
                replay = await r.xread({stream_key: last_event_id})
                for _, entries in replay:
                    for entry_id, fields in entries:
                        body = fields.get("body")
                        if not body:
                            continue
                        envelope = json.dumps({"id": entry_id, **json.loads(body)})
                        yield _sse_frame(entry_id, envelope)
            except Exception as exc:
                log.warning(
                    "glens.stream.replay_failed",
                    session_id=session_id,
                    last_event_id=last_event_id,
                    error=str(exc),
                )

        loop = asyncio.get_event_loop()
        last_activity = loop.time()

        while True:
            if await is_disconnected():
                break

            msg = await pubsub.get_message(
                ignore_subscribe_messages=True,
                timeout=PUBSUB_POLL_SECONDS,
            )
            if msg is not None:
                raw = msg.get("data") or ""
                try:
                    envelope = json.loads(raw)
                    yield _sse_frame(envelope.get("id", ""), raw)
                except Exception:
                    pass
                last_activity = loop.time()
            elif loop.time() - last_activity > IDLE_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_activity = loop.time()
    finally:
        try:
            await pubsub.unsubscribe(channel_key)
            await pubsub.close()
            await r.close()
        except Exception:
            pass


@router.get("/sessions/{session_id}/stream")
async def glens_session_stream(
    session_id: str,
    request: Request,
    last_event_id: str | None = Header(default=None, alias="Last-Event-Id"),
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """SSE stream of events for one Lens session.

    Auth: same permission as chat/stream + we assert the session belongs
    to the caller's workspace (`_get_session` 404s otherwise). This is
    the only door out — anyone opening it subscribes to every event on
    the session, so cross-workspace leakage must be impossible.
    """
    ws_uuid = _parse_workspace_id(workspace_id)
    _get_session(db, session_id, ws_uuid)  # 404 if not in workspace

    return StreamingResponse(
        _stream_events(session_id, last_event_id, request.is_disconnected),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: disable proxy buffering
        },
    )
