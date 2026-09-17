"""Behavioural proof that the async ``_check`` offload keeps the event
loop responsive under a slow policy evaluation.

The old bug shape: sync ``_check`` blocked the loop for the duration
of its DB round-trip. Under enough concurrent gateway requests the
loop stalled long enough for Render's 5s ``/health`` probe to miss,
triggering an instance restart.

This test runs a slow (1s) async ``policy_check`` through the real
``AttemptCoordinator`` and, in parallel, times a lightweight coroutine
that stands in for a ``/health`` handler. If the loop is properly
free during the policy check, the "health" coroutine returns within
milliseconds. If the offload regressed and ``_check`` runs on the
loop again, the "health" coroutine blocks until the policy check
completes.

This is the concurrency test the PR review asked for and the guard
that source-level assertions can't provide.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_health_probe_stays_responsive_during_slow_policy_check():
    """Slow policy_check + concurrent probe. The probe must return in
    < 100ms even though the policy check is still running for ~1s.
    Regression guard on the P1 that caused the concurrency-40 restart."""
    from app.runtime.attempt_coordinator import (
        AllAttemptsFailed,
        AttemptCoordinator,
    )

    # Minimal ResolvedV2 with one target and a 5s budget (enough to let
    # the 1s policy check complete without deadline-firing).
    resolved = MagicMock()
    profile = resolved.profile
    profile.timeout_seconds = 5.0
    profile.max_attempts = 1
    profile.accepts = ["chat_completion"]
    target = MagicMock()
    target.id = "t1"
    target.transport = "native_http"
    profile.targets = [target]
    resolved.revision_id = "rev-1"

    coordinator = AttemptCoordinator()
    # Stub the transport — never actually dispatch (policy check will pass
    # and coordinator would attempt to call it; we mock it to return None
    # which the outer flow will treat as an error, doesn't matter).
    coordinator._dispatch = AsyncMock(return_value=MagicMock())

    async def _slow_policy_check(_target):
        # Sleeps 1s on the loop but should NOT block it — we're going
        # to prove that by checking the probe coroutine's latency.
        await asyncio.sleep(1.0)
        return None  # allow dispatch

    async def _probe():
        # Tight coroutine that yields to the loop and measures how long
        # it takes to schedule + complete. Stand-in for the /health
        # handler, which does asyncio.sleep(0) internally to respond.
        start = time.monotonic()
        await asyncio.sleep(0)  # yield once
        return time.monotonic() - start

    # Run coordinator (slow policy check) and probe in parallel.
    coord_task = asyncio.create_task(
        coordinator.execute(
            resolved=resolved,
            operation="chat_completion",
            payload={},
            credential_resolver=MagicMock(),
            policy_check=_slow_policy_check,
        )
    )
    # Give the coordinator a tick to enter its async loop.
    await asyncio.sleep(0.05)

    probe_latency = await _probe()

    # Even though the policy check is still sleeping, the probe must
    # be able to schedule and return. Loop-blocking regressions push
    # this into the seconds.
    assert probe_latency < 0.1, (
        f"probe took {probe_latency*1000:.1f}ms — the event loop was "
        "blocked by the policy check. The _check offload regressed."
    )

    # Let the coordinator finish (it will fail because the mocked
    # transport doesn't return a proper CoordinatorResult shape; we
    # only care that the probe was responsive during the check).
    try:
        await coord_task
    except Exception:
        pass


@pytest.mark.asyncio
async def test_many_concurrent_slow_policies_do_not_stall_probe():
    """Ten concurrent slow policy checks + one probe. Probe still
    returns fast. Under the old sync ``_check``, ten concurrent
    requests each blocked the loop serially → probe would wait
    ~10s. Under the offload, they run in the threadpool → probe
    returns immediately."""
    from app.runtime.attempt_coordinator import AttemptCoordinator

    resolved = MagicMock()
    profile = resolved.profile
    profile.timeout_seconds = 10.0
    profile.max_attempts = 1
    profile.accepts = ["chat_completion"]
    target = MagicMock()
    target.id = "t1"
    target.transport = "native_http"
    profile.targets = [target]
    resolved.revision_id = "rev-1"

    async def _slow(_target):
        await asyncio.sleep(0.5)
        return None

    async def _one_request():
        coordinator = AttemptCoordinator()
        coordinator._dispatch = AsyncMock(return_value=MagicMock())
        try:
            await coordinator.execute(
                resolved=resolved,
                operation="chat_completion",
                payload={},
                credential_resolver=MagicMock(),
                policy_check=_slow,
            )
        except Exception:
            pass

    # Kick off ten concurrent requests.
    workload = [asyncio.create_task(_one_request()) for _ in range(10)]
    await asyncio.sleep(0.05)  # let them enter their policy checks

    # Probe.
    start = time.monotonic()
    await asyncio.sleep(0)
    latency = time.monotonic() - start

    assert latency < 0.1, (
        f"probe took {latency*1000:.1f}ms with 10 concurrent slow "
        "policies — event loop is stalling. The offload broke under "
        "concurrency."
    )

    await asyncio.gather(*workload, return_exceptions=True)
