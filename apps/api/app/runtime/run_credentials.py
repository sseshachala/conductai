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

# cred_token -> {handle: decrypted-creds-dict}
_CACHE: dict[str, dict[str, dict]] = {}


def populate(cred_token: str, credentials: dict[str, dict]) -> None:
    """Snapshot the decrypted credential map for this run segment."""
    if not cred_token:
        return
    _CACHE[cred_token] = dict(credentials)


def resolve(cred_token: str, handle: str) -> dict | None:
    """Cache lookup. Returns None on miss so callers can fall back to broker."""
    if not cred_token:
        return None
    return _CACHE.get(cred_token, {}).get(handle)


def purge(cred_token: str) -> None:
    """Drop the snapshot when the segment finishes."""
    if not cred_token:
        return
    _CACHE.pop(cred_token, None)
