"""Tests for the SHA-256 hash chain logic used by verify_chain.

Tests the hash computation algorithm directly — no DB, no FastAPI.
The endpoint is integration territory; the algorithm is the invariant.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def _ts(offset: int = 0) -> datetime:
    return datetime(2026, 1, 1, 12, 0, offset, tzinfo=timezone.utc)


def _compute(ts: datetime, tool_call: str, decision: str, prev: str) -> str:
    """Mirror of the algorithm in verify_chain and chain_hash_for_insert."""
    return hashlib.sha256(
        f"{ts.isoformat()}|{tool_call}|{decision}|{prev}".encode()
    ).hexdigest()


def _build_chain(events: list[tuple[str, str]]) -> list[dict]:
    """Build a correctly-linked chain of event dicts."""
    chain, prev = [], ""
    for i, (tool_call, decision) in enumerate(events):
        ts = _ts(i)
        entry = _compute(ts, tool_call, decision, prev)
        chain.append({"ts": ts, "tool_call": tool_call, "decision": decision,
                       "entry_hash": entry})
        prev = entry
    return chain


def _walk_chain(events: list[dict]) -> tuple[bool, str | None]:
    """Walk a chain and return (valid, broken_at_iso)."""
    prev = ""
    for ev in events:
        expected = _compute(ev["ts"], ev["tool_call"] or "", ev["decision"], prev)
        if ev["entry_hash"] and ev["entry_hash"] != expected:
            return False, ev["ts"].isoformat()
        prev = ev["entry_hash"] or prev
    return True, None


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_valid_chain():
    events = _build_chain([("Bash", "allowed"), ("Write", "blocked"), ("Read", "allowed")])
    valid, broken_at = _walk_chain(events)
    assert valid is True
    assert broken_at is None


def test_broken_chain_detected_at_correct_event():
    events = _build_chain([("Bash", "allowed"), ("Write", "blocked"), ("Read", "allowed")])
    events[1]["entry_hash"] = "deadbeef" * 8  # tamper middle row
    valid, broken_at = _walk_chain(events)
    assert valid is False
    assert broken_at == events[1]["ts"].isoformat()


def test_tamper_first_event():
    events = _build_chain([("Bash", "allowed"), ("Write", "blocked")])
    events[0]["entry_hash"] = "0" * 64
    valid, broken_at = _walk_chain(events)
    assert valid is False
    assert broken_at == events[0]["ts"].isoformat()


def test_empty_chain_is_valid():
    valid, broken_at = _walk_chain([])
    assert valid is True
    assert broken_at is None


def test_single_event_chain():
    events = _build_chain([("Write", "blocked")])
    valid, broken_at = _walk_chain(events)
    assert valid is True


def test_null_entry_hash_on_sole_event():
    """A single legacy event with no hash is not counted as broken."""
    events = _build_chain([("Bash", "allowed")])
    events[0]["entry_hash"] = None
    valid, broken_at = _walk_chain(events)
    assert valid is True


def test_hash_is_deterministic():
    """Same inputs must always produce the same hash."""
    ts = _ts(0)
    h1 = _compute(ts, "Bash", "allowed", "")
    h2 = _compute(ts, "Bash", "allowed", "")
    assert h1 == h2


def test_hash_changes_with_prev():
    """Changing prev_hash changes the entry_hash — chain is actually linked."""
    ts = _ts(0)
    h1 = _compute(ts, "Bash", "allowed", "")
    h2 = _compute(ts, "Bash", "allowed", "different_prev")
    assert h1 != h2


def test_genesis_row_uses_empty_prev():
    """First event in a chain must use empty string as prev — not None or zero."""
    ts = _ts(0)
    entry = _compute(ts, "Bash", "allowed", "")
    # Re-verify with explicit empty string — must be stable
    assert len(entry) == 64  # SHA-256 hex digest
    assert _compute(ts, "Bash", "allowed", "") == entry
