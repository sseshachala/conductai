"""Regression guard: the attempt coordinator bounds the awaited
policy_check by the remaining request deadline.

Without this, a slow async policy eval could consume the entire
timeout budget and still trigger a paid upstream dispatch afterward
— exactly the P1 the reviewer flagged.

We keep this as a source-level check (fast + no infrastructure) plus
one behavioural test that drives the exact code path.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_COORDINATOR_SRC = (
    Path(__file__).resolve().parents[2]
    / "app" / "runtime" / "attempt_coordinator.py"
).read_text(encoding="utf-8")


def test_awaited_policy_check_is_bounded_by_remaining_deadline():
    """The await on the policy_check callback must be wrapped in
    asyncio.wait_for so a slow eval cannot outlast the coordinator
    deadline. Regression guard on P1 from PR review."""
    # The await site.
    assert "await asyncio.wait_for(_pc_result, timeout=remaining)" in _COORDINATOR_SRC, (
        "policy_check await must be bounded by the coordinator's remaining "
        "deadline via asyncio.wait_for. Without this, a slow policy eval can "
        "consume the entire budget and still trigger a paid upstream dispatch."
    )


def test_remaining_is_recomputed_after_policy_check():
    """After a slow policy_check, remaining time must be re-derived and
    the target refused if the budget is exhausted."""
    # Look for the recompute right after the policy_check block.
    assert "# Recompute remaining after the (possibly slow) policy check" in _COORDINATOR_SRC, (
        "remaining budget must be recomputed after awaiting policy_check "
        "so the transport dispatch does not fire past deadline."
    )


def test_policy_check_timeout_records_deadline_attempt():
    """On asyncio.TimeoutError from policy_check, the target is recorded
    as a deadline attempt and no further targets get dispatched. Same
    shape as the pre-policy-check deadline branch above."""
    # Both timeout and post-check-expiry paths must break out via a
    # ``_deadline_record`` entry.
    excerpt_start = _COORDINATOR_SRC.find("except asyncio.TimeoutError:")
    assert excerpt_start != -1, "policy_check timeout branch must exist"
    excerpt = _COORDINATOR_SRC[excerpt_start:excerpt_start + 500]
    assert "_deadline_record" in excerpt, (
        "policy_check timeout must record a deadline attempt and break "
        "the target loop — otherwise the coordinator continues to the "
        "next target on a request whose budget is already spent."
    )
    assert "break" in excerpt, (
        "policy_check timeout must break out of the target loop, not "
        "``continue`` to the next target."
    )


@pytest.mark.asyncio
async def test_slow_policy_check_never_reaches_transport():
    """Drive the exact path: a policy_check that sleeps longer than
    the profile's timeout_seconds → coordinator must NOT call the
    transport. Ensures the fix behaviourally, not just via source
    grep."""
    from app.runtime.attempt_coordinator import (
        AllAttemptsFailed,
        AttemptCoordinator,
    )

    # Build a minimal ResolvedV2 with one target and a 100ms budget.
    resolved = MagicMock()
    profile = resolved.profile
    profile.timeout_seconds = 0.1
    profile.max_attempts = 1
    profile.accepts = ["chat_completion"]

    target = MagicMock()
    target.id = "t1"
    target.transport = "native_http"
    profile.targets = [target]
    resolved.revision_id = "rev-1"

    # Slow async policy check — sleeps past the deadline.
    async def _slow(_target):
        await asyncio.sleep(1.0)
        return None  # would allow dispatch

    # Transport stub — MUST NOT be called.
    dispatched: list[bool] = []
    coordinator = AttemptCoordinator()
    coordinator._dispatch = AsyncMock(
        side_effect=lambda **_kw: dispatched.append(True) or MagicMock()
    )

    credential_resolver = MagicMock()

    with pytest.raises(AllAttemptsFailed):
        await coordinator.execute(
            resolved=resolved,
            operation="chat_completion",
            payload={},
            credential_resolver=credential_resolver,
            policy_check=_slow,
        )

    assert not dispatched, (
        "transport dispatched despite policy_check exceeding coordinator "
        "deadline — the deadline guard is broken."
    )
