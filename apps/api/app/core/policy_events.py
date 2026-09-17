"""Publisher helpers for policy invalidation events.

Every writer that mutates composed-policy state calls one of these so
consumers (the effective-policy cache on peer workers) drop cached
entries within bus-delivery latency instead of waiting the TTL.

Event kinds:

- ``guard.policy.invalidated`` — one workspace's composed rules changed.
- ``guard.pack.updated`` — a skill pack version bumped or was installed/
  removed. Publisher cannot cheaply enumerate the workspaces that
  installed the pack, so consumers drop every entry (sledgehammer; the
  event itself is rare).

Losing a publish is not a correctness bug; the cache's TTL is the
correctness ceiling.
"""
from __future__ import annotations

from app.core.bus_publish import fire


def publish_policy_invalidated(workspace_id: str) -> None:
    fire("guard.policy.invalidated", str(workspace_id))


def publish_pack_updated(pack_slug: str) -> None:
    fire("guard.pack.updated", str(pack_slug))
