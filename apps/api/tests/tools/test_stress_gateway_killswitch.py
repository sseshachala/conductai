"""Regression guard for scripts/stress_gateway.py.

Original invariant (R14, pre-#2141): every task loop had to re-check
BOTH the kill-switch flag AND the wall-clock deadline before and after
the semaphore — otherwise queued tasks could dispatch past a stop.

PR #2141 rewrite: the wall-clock check moved OUT of the per-task loop
and INTO ``asyncio.wait_for`` wrapping the gather. That gives a real
overall deadline (reviewer P1 #2) — the previous per-task check only
stopped NEW dispatch, not in-flight work. The invariant the old tests
guarded now takes a different shape:

  - Per-task loop still guards against post-kill-switch dispatch via
    ``stop_reason`` check, both before AND after ``async with sem``.
  - Overall deadline is guaranteed by ``asyncio.wait_for(..., timeout=
    max_wall)`` at the gather layer.
  - The old ``'error_rate'`` label split into ``'admitted_error_rate'``
    (real fault axis) and ``'rejection_rate'`` (backpressure axis).

These tests assert the new invariants so future refactors can't
silently regress either guarantee.
"""
from __future__ import annotations

from pathlib import Path


_STRESS = (
    Path(__file__).resolve().parents[4]
    / "scripts" / "stress_gateway.py"
).read_text(encoding="utf-8")


def test_stop_condition_rechecked_after_semaphore_acquire():
    """After ``async with sem`` acquires the semaphore, the inner body
    must re-evaluate the kill-switch so queued tasks can't dispatch
    once the stop condition has fired."""
    idx = _STRESS.index("async with sem:")
    body = _STRESS[idx : idx + 400]
    assert "stop_reason is not None" in body and "return" in body, (
        "post-acquire kill-switch re-check missing inside "
        "``async with sem`` block. Without it, queued tasks continue "
        "firing requests after ``stop_reason`` is set."
    )


def test_stop_condition_also_precheck():
    """A post-acquire check alone would let every queued task pay the
    semaphore-wait latency before short-circuiting. Pre-acquire cheap
    check must remain."""
    idx = _STRESS.index("async with sem:")
    prelude = _STRESS[max(0, idx - 400) : idx]
    assert "stop_reason is not None" in prelude, (
        "pre-acquire kill-switch check missing before ``async with "
        "sem`` block. Every queued task would pay semaphore-wait "
        "latency for nothing during a real incident."
    )


def test_overall_deadline_via_wait_for():
    """PR #2141 P1 #2: ``--max-wall`` must be a REAL overall deadline
    that also cancels in-flight tasks. The previous per-task check only
    stopped NEW dispatch. Enforce that the gather is wrapped in
    ``asyncio.wait_for(..., timeout=max_wall)``."""
    assert "asyncio.wait_for(" in _STRESS, (
        "overall deadline must be enforced via asyncio.wait_for around "
        "the gather, not a per-task loop check. Otherwise --max-wall "
        "doesn't stop in-flight requests (reviewer P1 #2)."
    )
    # And it must be parameterised by max_wall.
    idx = _STRESS.index("asyncio.wait_for(")
    call = _STRESS[idx : idx + 200]
    assert "max_wall" in call, (
        "asyncio.wait_for must use ``timeout=max_wall`` so the whole-"
        "run deadline is honored."
    )


def test_stop_reason_labels_are_named():
    """Report must be able to distinguish which threshold fired.
    PR #2141 split the old ``'error_rate'`` into two axes — admitted-
    error (real fault) vs rejection-rate (backpressure) — plus the
    existing wall-clock stop. All three labels must appear as literal
    strings so ``_report`` can name the actual stop cause."""
    for label in ("wall_clock", "admitted_error_rate", "rejection_rate"):
        assert f'"{label}"' in _STRESS or f"'{label}'" in _STRESS, (
            f"stress script must emit stop_reason={label!r} at the "
            "matching branch so _report can print the accurate line "
            "instead of reconstructing the reason from statuses."
        )
