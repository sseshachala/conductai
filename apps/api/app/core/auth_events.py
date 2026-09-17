"""Publisher helpers for auth invalidation events.

Every DB writer that changes authorization state calls one of these
so the auth cache (PR 6b) drops the affected entries within the
bus-delivery latency (typically milliseconds) instead of waiting the
full TTL for the bounded-refresh path to notice.

Losing a publish is not a correctness bug — the cache's TTL is the
correctness ceiling. Publishers are the fast path only. They MUST be
fire-and-forget and MUST NOT block or fail the writer request.

Each helper corresponds to one invalidation event kind the AuthCache
subscribes to:

- ``token.revoked``     → ``invalidate_fingerprint(fp)``
- ``identity.disabled`` → ``invalidate_identity(id)``
- ``risk_tier.changed`` → ``invalidate_identity(id)``
- ``permission.changed`` → ``invalidate_workspace(ws)``
- ``workspace.changed`` → ``invalidate_workspace(ws)``
"""
from __future__ import annotations

import asyncio
import hashlib

import structlog

log = structlog.get_logger()


def _fingerprint(token: str) -> str:
    """Same hash function the cache uses to key entries. Publisher
    side computes the fingerprint from the raw token being revoked;
    consumer side compares against its stored fingerprints."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _fire(kind: str, key: str, version: int = 0) -> None:
    """Publish to the invalidation bus without awaiting. Safe to call
    from sync request handlers — schedules the publish on the running
    event loop as a fire-and-forget task.

    If no loop is running (rare — background workers) this is a no-op;
    the cache falls back to its bounded refresh."""
    try:
        from app.core.invalidation_bus import get_bus
        bus = get_bus()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.debug("auth_events.no_running_loop", kind=kind, key=key)
            return
        loop.create_task(bus.publish(kind, key, version))
    except Exception as e:  # noqa: BLE001
        log.warning("auth_events.publish_scheduling_failed", kind=kind, err=str(e))


def publish_token_revoked(raw_token: str) -> None:
    """Emit ``auth.token.revoked`` with the token's fingerprint."""
    _fire("auth.token.revoked", _fingerprint(raw_token))


def publish_fingerprint_revoked(fp: str) -> None:
    """Emit ``auth.token.revoked`` when only the fingerprint is
    available (e.g. bulk-revocation queries that don't hold the raw
    token)."""
    _fire("auth.token.revoked", fp)


def publish_identity_disabled(agent_identity_id: str) -> None:
    """Emit ``auth.identity.disabled``. Drops every cached auth entry
    for the identity — used on lifecycle_state transitions to
    ``deactivated`` / ``expired`` and on identity deletion."""
    _fire("auth.identity.disabled", agent_identity_id)


def publish_risk_tier_changed(agent_identity_id: str) -> None:
    """Emit ``auth.risk_tier.changed``. Drops every cached auth entry
    for the identity — a tier change alters gate decisions so cached
    tier values must not survive."""
    _fire("auth.risk_tier.changed", agent_identity_id)


def publish_permission_changed(workspace_id: str) -> None:
    """Emit ``auth.permission.changed``. Drops every cached auth
    entry in the workspace — permission scope is workspace-wide."""
    _fire("auth.permission.changed", workspace_id)


def publish_workspace_changed(workspace_id: str) -> None:
    """Emit ``auth.workspace.changed``. Drops every cached auth entry
    in the workspace — used on membership / workspace-config changes."""
    _fire("auth.workspace.changed", workspace_id)
