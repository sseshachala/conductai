"""Regression guard for scripts/stress_gateway.py — kill switch must
recheck stop conditions AFTER acquiring the semaphore. Without this,
tasks that queued for the semaphore before the switch fired continue
to dispatch and hammer a broken upstream during a real incident.

Source-level guard is enough — the script itself doesn't ship a
callable API and running the real script against a mock server per
test would be overkill.
"""
from __future__ import annotations

from pathlib import Path


_STRESS = (
    Path(__file__).resolve().parents[4]
    / "scripts" / "stress_gateway.py"
).read_text(encoding="utf-8")


def test_kill_switch_rechecked_after_semaphore_acquire():
    """The stop-condition (kill flag + wall-clock deadline) must be
    re-evaluated after ``async with sem`` acquires the semaphore. If
    it were only checked before ``async with sem``, tasks queued for
    the semaphore during a healthy-looking window would still
    dispatch after the kill switch fired."""
    # Locate the semaphore-acquire block.
    idx = _STRESS.index("async with sem:")
    # Find the next 500 chars of the body — that's where the recheck
    # must live for the script to be race-free.
    body = _STRESS[idx:idx + 500]
    assert "if kill or time.monotonic() - started > max_wall:" in body, (
        "kill-switch recheck missing inside ``async with sem`` block. "
        "Without a post-acquire check, queued tasks continue firing "
        "requests after the switch fires. See PR review P1."
    )


def test_kill_switch_does_not_only_precheck():
    """A pre-acquire check alone is not enough — it races with the
    semaphore queue. The comment in the script must reflect the
    two-phase pattern so future edits don't collapse it back to the
    broken single-check form."""
    assert "Re-check AFTER acquiring the semaphore" in _STRESS, (
        "kill-switch fix must be documented in a code comment; a bare "
        "duplicate check without explaining the race invites a well-"
        "meaning future edit to dedupe it and reintroduce the bug."
    )
