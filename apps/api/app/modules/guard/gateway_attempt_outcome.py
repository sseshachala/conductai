"""Attempt-outcome helpers for ``handle_gateway_request`` (#2403).

Kept out of ``gateway_handler.py`` (already over the 500-line budget).

- ``idempotent_request_id``: #2057 invariant 4 (retries are idempotent
  or refused). A client ``X-Request-Id`` is hashed with the workspace
  and principal into the server-owned request id. The durable
  acceptance row's unique ``request_id`` index then refuses a repeat
  before any reservation or dispatch.
- ``wrap_stream_finally``: run one cleanup exactly once when a streaming
  body ends (drained, client disconnect, or upstream error).
"""
from __future__ import annotations

import uuid
from typing import Awaitable, Callable

# Fixed namespace so the same (workspace, principal, key) always maps to
# the same request id across workers and restarts.
_IDEMPOTENCY_NAMESPACE = uuid.UUID("5d0c7a52-7f2e-4f43-9a4e-24030a1d0000")


def idempotent_request_id(
    *,
    workspace_id: str,
    clerk_user_id: str | None,
    agent_identity_id: str | None,
    client_key: str | None,
) -> str | None:
    """Deterministic server request id for a client idempotency key.

    Scoped by workspace and principal, so one tenant's key can never
    collide with (or reveal) another tenant's request. ``None`` when the
    client sent no key: the caller mints a random id as before.
    """
    if not client_key:
        return None
    scope = "\x1f".join((
        str(workspace_id), str(clerk_user_id or ""), str(agent_identity_id or ""), client_key,
    ))
    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, scope))


def wrap_stream_finally(response, cleanup: Callable[[], Awaitable[None]]):
    """Run ``cleanup`` exactly once after the streaming body ends.

    Closes the inner iterator first, so inner wrappers (finalize,
    receipts, settlement) complete before the cleanup fires.
    """
    original = response.body_iterator

    async def iterator():
        try:
            async for chunk in original:
                yield chunk
        finally:
            import anyio
            with anyio.CancelScope(shield=True):
                try:
                    close = getattr(original, "aclose", None)
                    if close:
                        await close()
                finally:
                    await cleanup()

    response.body_iterator = iterator()
    return response
