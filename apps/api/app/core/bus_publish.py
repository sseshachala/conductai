"""Shared fire-and-forget publisher for invalidation events.

Used by ``policy_events`` (and, post-merge, ``auth_events``). Consolidates
the ``get_bus() + loop.create_task(publish)`` boilerplate so writers can
emit invalidations in one line without repeating the loop-detection dance.

Losing a publish is never a correctness bug — every consumer cache has
a bounded-refresh path that recovers on TTL. This helper therefore never
raises to the caller.
"""
from __future__ import annotations

import asyncio

import structlog

log = structlog.get_logger()


def fire(kind: str, key: str, version: int = 0) -> None:
    """Schedule a bus publish without awaiting. Safe to call from sync
    request handlers. No-op if no event loop is running."""
    try:
        from app.core.invalidation_bus import get_bus
        bus = get_bus()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            log.debug("bus_publish.no_running_loop", kind=kind, key=key)
            return
        loop.create_task(bus.publish(kind, key, version))
    except Exception as e:  # noqa: BLE001
        log.warning("bus_publish.scheduling_failed", kind=kind, err=str(e))
