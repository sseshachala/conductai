"""Process-local credential cache for in-process runtime callers.

The executor fetches every workspace credential from the DB once at run
start (`get_all_credentials`). Blocks then re-fetched each handle they
needed via HTTP round-trip to `POST /credentials/creds/retrieve` — one
per handle per block, using the run's `cred_token` for auth.

That per-block broker call was two things at once:

1. Redundant — the worker already has decrypted creds in memory.
2. A silent-failure surface — `fetch_credential` swallows any non-200
   into an empty dict, which downstream (brain_block, etc.) then reads
   as "no key configured" and raises MissingProviderKey. Seen live on
   run resume when the cred_token had been invalidated by the previous
   segment's finally-block (bug B in the audit).

This module holds the decrypted creds in a process-local dict keyed by
the run's cred_token. `fetch_credential` consults this cache first and
only falls through to the broker for out-of-process callers (CLI, remote
workers, or the vanishingly rare cache-miss window).

Populated at executor init, purged when the segment ends. Nothing here
touches state / DB — pause/resume gets a fresh populate on the next
segment.
"""
from __future__ import annotations

import os
import time

# Coarse TTL cap so a rotated credential or an invalidated run token can't
# be served indefinitely by an in-process cache. The broker still enforces
# per-call expiry + use-count; this only bounds the STALENESS window when
# the cache short-circuits the broker. Tune via env if a long-running run
# genuinely needs a longer cache window; default is a compromise between
# hit-rate on the hot path and freshness under rotation (#2054 P1-3).
_CACHE_TTL_SEC = float(os.environ.get("RUN_CREDENTIALS_CACHE_TTL_SEC", "60"))

# cred_token -> (populated_at, {handle: decrypted-creds-dict})
_CACHE: dict[str, tuple[float, dict[str, dict]]] = {}


def populate(cred_token: str, credentials: dict[str, dict]) -> None:
    """Snapshot the decrypted credential map for this run segment."""
    if not cred_token:
        return
    _CACHE[cred_token] = (time.monotonic(), dict(credentials))


def resolve(cred_token: str, handle: str) -> dict | None:
    """Cache lookup. Returns None on miss OR on TTL expiry so callers fall
    through to the broker (which re-verifies expiry + use-count)."""
    if not cred_token:
        return None
    entry = _CACHE.get(cred_token)
    if entry is None:
        return None
    populated_at, snapshot = entry
    if time.monotonic() - populated_at > _CACHE_TTL_SEC:
        # Stale — force a broker round-trip so a rotated credential or an
        # invalidated run token is caught. Don't purge here so a concurrent
        # populate can refresh the snapshot in-place.
        return None
    return snapshot.get(handle)


def purge(cred_token: str) -> None:
    """Drop the snapshot when the segment finishes."""
    if not cred_token:
        return
    _CACHE.pop(cred_token, None)
