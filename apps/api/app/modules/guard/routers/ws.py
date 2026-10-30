"""
WebSocket endpoint for conduct-daemon policy push.

GET /guard/ws/policy?workspace_id=<uuid>&token=<api_key>

When invalidate_policy_cache() fires it publishes to Redis channel
"guard:policy:invalidated:<workspace_id>". Daemons subscribed to that
workspace receive a push and re-fetch /sync, keeping local SQLite fresh
without polling.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import redis as _redis_sync
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.auth import resolve_agent_token
from app.core.config import settings
from app.core.database import SessionLocal

LOG    = logging.getLogger("guard.ws")
router = APIRouter()

CHANNEL_PREFIX = "guard:policy:invalidated"

_pool: _redis_sync.ConnectionPool | None = None


def _r() -> _redis_sync.Redis:
    global _pool
    if _pool is None:
        _pool = _redis_sync.ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return _redis_sync.Redis(connection_pool=_pool)


# ── Token validation (sync, runs in executor) ─────────────────────────────────

def _token_workspace(token: str) -> str | None:
    """Return the workspace id the token resolves to, or None if invalid."""
    if not token:
        return None
    db = SessionLocal()
    try:
        resolved = resolve_agent_token(token, db)
        return str(resolved[0]) if resolved else None
    except Exception:
        return None
    finally:
        db.close()


def _token_valid(token: str) -> bool:
    return _token_workspace(token) is not None


# ── Publish (called by invalidate_policy_cache) ───────────────────────────────

def publish_policy_invalidated(workspace_id: uuid.UUID) -> None:
    """Fire-and-forget Redis publish. Called from invalidate_policy_cache()."""
    try:
        _r().publish(f"{CHANNEL_PREFIX}:{workspace_id}", json.dumps({
            "type": "policy_invalidated",
            "workspace_id": str(workspace_id),
        }))
    except Exception as e:
        LOG.warning("redis publish failed: %s", e)


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@router.websocket("/guard/ws/policy")
async def policy_ws(
    websocket: WebSocket,
    workspace_id: str = Query(...),
    token: str        = Query(""),
):
    loop = asyncio.get_event_loop()

    # Auth in executor — keeps event loop unblocked
    token_ws = await loop.run_in_executor(None, _token_workspace, token)
    if token_ws is None:
        await websocket.close(code=4001)
        return

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        await websocket.close(code=4002)
        return

    # The token must belong to the workspace being subscribed to.
    try:
        token_ws_uuid = uuid.UUID(token_ws)
    except ValueError:
        await websocket.close(code=1008)
        return
    if token_ws_uuid != ws_uuid:
        await websocket.close(code=1008)
        return

    await websocket.accept()
    channel = f"{CHANNEL_PREFIX}:{ws_uuid}"

    pubsub = _r().pubsub()
    pubsub.subscribe(channel)
    LOG.info("daemon connected for workspace %s", ws_uuid)

    try:
        while True:
            msg = await loop.run_in_executor(None, pubsub.get_message, True, 1.0)
            if msg and msg["type"] == "message":
                await websocket.send_text(msg["data"])
            else:
                try:
                    await websocket.send_text('{"type":"ping"}')
                except WebSocketDisconnect:
                    break
                await asyncio.sleep(15)
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
        LOG.info("daemon disconnected for workspace %s", ws_uuid)
