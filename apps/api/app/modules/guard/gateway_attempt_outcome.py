"""Attempt-outcome helpers for ``handle_gateway_request`` (#2403).

Kept out of ``gateway_handler.py`` (already over the 500-line budget).

- ``idempotent_request_id``: #2057 invariant 4 (retries are idempotent
  or refused). A client ``X-Request-Id`` is hashed with the workspace
  and principal into the server-owned request id. The durable
  acceptance row's unique ``request_id`` index then refuses a repeat
  before any reservation or dispatch.
"""
from __future__ import annotations

import uuid

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
