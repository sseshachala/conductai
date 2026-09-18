"""Regression guard for scripts/stress_gateway.py — the stop-condition
must be re-evaluated AFTER acquiring the semaphore, not just before.

Without a post-acquire re-check, tasks queued for the semaphore during
a healthy-looking window continue to dispatch after the stop condition
fires (kill switch or wall-clock deadline).

R14 rewrite (post-Fix 8 #2106): the previous tests asserted literal
strings ('kill or time.monotonic...' and 'Re-check AFTER acquiring the
semaphore') that Fix 8 renamed / removed. The invariant they were
guarding is still true — it is just expressed with ``stop_reason``
instead of the boolean ``kill``. These tests now check the structural
invariant instead of the exact variable name so a future rename does
not break the guard again.
"""
from __future__ import annotations

from pathlib import Path


_STRESS = (
    Path(__file__).resolve().parents[4]
    / "scripts" / "stress_gateway.py"
).read_text(encoding="utf-8")


# Identifiers that any 'stop' state check must include. Post-Fix 8 that
# is ``stop_reason``; pre-Fix 8 it was ``kill``. Accept either so a
# rename does not re-break the test.
_STOP_STATE_TOKENS = ("stop_reason", "kill")


def _has_stop_check(block: str) -> bool:
    """Return True if `block` contains a stop-state check paired with the
    wall-clock deadline. Both stop signals must appear so a caller can't
    reintroduce the single-condition form."""
    stop_matched = any(tok in block for tok in _STOP_STATE_TOKENS)
    deadline_matched = "time.monotonic() - started > max_wall" in block
    return stop_matched and deadline_matched


def test_stop_condition_rechecked_after_semaphore_acquire():
    """After ``async with sem`` acquires the semaphore, the inner body
    must re-evaluate both stop signals so queued tasks can't dispatch
    once the stop condition has fired."""
    idx = _STRESS.index("async with sem:")
    body = _STRESS[idx : idx + 500]
    assert _has_stop_check(body), (
        "post-acquire stop check missing inside ``async with sem`` block. "
        "Without a re-check, queued tasks continue firing requests after "
        "the stop condition fires. See PR review R14 / P1."
    )


def test_stop_condition_also_precheck():
    """A post-acquire check alone would let every queued task pay the
    semaphore-wait latency before short-circuiting. The two-phase pattern
    (pre-acquire cheap + post-acquire authoritative) must remain."""
    idx = _STRESS.index("async with sem:")
    prelude = _STRESS[max(0, idx - 400) : idx]
    assert _has_stop_check(prelude), (
        "pre-acquire stop check missing before ``async with sem`` block. "
        "Every queued task paying the semaphore-wait latency for nothing "
        "would fill the connection pool during a real incident. See PR "
        "review R14 / P1."
    )


def test_stop_reason_names_the_actual_stop():
    """Report must be able to distinguish wall-clock vs error-rate stops.
    Post-Fix 8 the state is a string 'wall_clock' | 'error_rate' | None
    so the report can name the actual stop cause instead of inferring it
    from the final status counts.

    R14 asserts the state value shape survives future refactors."""
    for label in ("wall_clock", "error_rate"):
        assert f'"{label}"' in _STRESS or f"'{label}'" in _STRESS, (
            f"stress script must emit stop_reason={label!r} at the "
            "matching branch so _report can print the accurate line "
            "instead of reconstructing the reason from statuses."
        )
