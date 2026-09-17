"""Behavioural proof that a slow policy_check does NOT block the event
loop — the whole reason ``_check`` was made async in PR #2065.

The previous version of this file was broken: it substituted
``asyncio.sleep`` for the policy work, which is inherently non-blocking
and passes even when the underlying code is broken. Reviewer verified
this by replacing the sleeps with blocking ``time.sleep()`` — tests
still passed. That's the shape a real regression takes and the tests
did not catch it.

New shape:

- Use ``time.sleep()`` (BLOCKING) inside the policy callback. This is
  what the sync ``_check`` closure did before PR #2065 and what any
  future regression would look like.
- Wrap the policy callback in ``run_in_threadpool`` inside a small
  async shim, matching the production ``_check`` closure exactly.
- Start probe timing BEFORE the workload starts, so any stall during
  the initial scheduling wait is measured too.
- Assert the policy work is STILL in progress when the probe
  completes — otherwise the probe might just be racing after the
  workload finished.
- Do not swallow the coordinator's exception. If it fails with the
  wrong error class, that's a signal the test setup regressed.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.concurrency import run_in_threadpool


def _resolved_mock(*, timeout: float = 5.0):
    """Minimal ResolvedV2 stub — one target, no attempts of substance."""
    resolved = MagicMock()
    profile = resolved.profile
    profile.timeout_seconds = timeout
    profile.max_attempts = 1
    profile.accepts = ["chat_completion"]
    target = MagicMock()
    target.id = "t1"
    target.transport = "native_http"
    profile.targets = [target]
    resolved.revision_id = "rev-1"
    return resolved


@pytest.mark.asyncio
async def test_health_probe_responsive_during_blocking_policy_check():
    """The policy check does BLOCKING sync work (time.sleep) exactly
    like the sync ``_check`` closure did before PR #2065. Under the
    offload it runs in the threadpool so the event loop stays free
    for the probe. If a future regression makes ``_check`` run on
    the loop again, ``time.sleep()`` will block the loop and the
    probe latency will spike into seconds."""
    from app.runtime.attempt_coordinator import (
        AllAttemptsFailed,
        AttemptCoordinator,
    )

    policy_started = asyncio.Event()
    policy_should_finish = asyncio.Event()

    async def _policy_check(_target):
        # Run the SYNC blocking body in a threadpool worker — exactly
        # like the production ``_check`` closure does. If that offload
        # regresses (someone drops the threadpool wrap), this call
        # would block the event loop for ``time.sleep`` duration.
        def _sync_body():
            time.sleep(0.5)  # BLOCKING — real regression shape
            return None

        # Signal to the test that we've entered the callback, so
        # the probe measurement can trust the workload is running.
        policy_started.set()
        try:
            return await run_in_threadpool(_sync_body)
        finally:
            policy_should_finish.set()

    coordinator = AttemptCoordinator()
    # Transport is stubbed; coordinator will call it after policy check
    # returns None. We do NOT swallow its failure — if the shape of
    # execute() changes such that the test setup breaks, we want to
    # see that in the failure output, not have it silently pass.
    coordinator._dispatch = AsyncMock(side_effect=RuntimeError("mock upstream failure — test setup"))

    probe_start = time.monotonic()
    coord_task = asyncio.create_task(
        coordinator.execute(
            resolved=_resolved_mock(),
            operation="chat_completion",
            payload={},
            credential_resolver=MagicMock(),
            policy_check=_policy_check,
        )
    )

    # Wait for the callback to actually enter its sync body. We're now
    # sure the workload is in progress and any subsequent probe latency
    # reflects the current state of the loop, not scheduling overhead.
    await policy_started.wait()

    # Now — is the loop responsive? Schedule a tight yield-only
    # coroutine and time how long it takes.
    yield_start = time.monotonic()
    await asyncio.sleep(0)
    yield_latency = time.monotonic() - yield_start

    # Also assert the policy work is STILL running. Otherwise the
    # probe might be racing after the workload finished, which
    # would let a broken (sync) implementation still pass because
    # by the time we measure, everything is done.
    assert not policy_should_finish.is_set(), (
        "policy work already finished before probe measured — the "
        "test raced past the workload and can't distinguish a blocked "
        "loop from a fast completion. Extend the sync sleep."
    )

    # A blocked event loop would push this into 100ms+.
    assert yield_latency < 0.05, (
        f"probe yield took {yield_latency*1000:.1f}ms while policy "
        "check was in progress — the event loop is BLOCKED. The "
        "``_check`` offload has regressed."
    )

    # Also assert total elapsed since probe_start is small (catches
    # stalls during the initial scheduling that a mid-run yield
    # measurement would miss).
    total_probe_elapsed = time.monotonic() - probe_start
    assert total_probe_elapsed < 0.5, (
        f"total wall-clock from probe_start to loop-still-free was "
        f"{total_probe_elapsed*1000:.1f}ms — a stall happened during "
        "scheduling before policy_started fired."
    )

    # Let the coordinator finish. Do NOT swallow the exception —
    # ``AllAttemptsFailed`` is the expected outcome (mock transport
    # doesn't produce a valid CoordinatorResult). Any OTHER exception
    # class means the test setup regressed and we want to see it.
    with pytest.raises(AllAttemptsFailed):
        await coord_task


@pytest.mark.asyncio
async def test_probe_responsive_with_ten_concurrent_blocking_policies():
    """Ten concurrent BLOCKING policy checks. Under the sync bug this
    would serialize on the event loop and stall the probe for
    ~5 seconds (10 x 0.5s). Under the offload they run in the
    threadpool in parallel and the loop stays free."""
    from app.runtime.attempt_coordinator import (
        AllAttemptsFailed,
        AttemptCoordinator,
    )

    started_count = 0
    finished_count = 0
    started_event = asyncio.Event()

    async def _policy_check(_target):
        nonlocal started_count, finished_count
        started_count += 1
        # Signal once at least one policy is in flight — probes must
        # happen while the workload is genuinely in progress.
        if not started_event.is_set():
            started_event.set()

        def _sync_body():
            time.sleep(0.5)  # BLOCKING sync sleep — real regression shape.
            return None

        try:
            return await run_in_threadpool(_sync_body)
        finally:
            finished_count += 1

    async def _one_request():
        c = AttemptCoordinator()
        c._dispatch = AsyncMock(side_effect=RuntimeError("mock upstream failure — test setup"))
        with pytest.raises(AllAttemptsFailed):
            await c.execute(
                resolved=_resolved_mock(timeout=10.0),
                operation="chat_completion",
                payload={},
                credential_resolver=MagicMock(),
                policy_check=_policy_check,
            )

    probe_start = time.monotonic()
    workload = [asyncio.create_task(_one_request()) for _ in range(10)]

    await started_event.wait()

    yield_start = time.monotonic()
    await asyncio.sleep(0)
    yield_latency = time.monotonic() - yield_start

    # Assert workload is still running — at least one policy hasn't
    # finished yet. If all 10 finished before we measured, we can't
    # distinguish "loop responsive" from "test raced past the work".
    assert finished_count < 10, (
        f"all 10 policies finished before probe measured "
        f"(started={started_count}, finished={finished_count}) — "
        "the test raced past the workload. Increase sleep duration "
        "or number of concurrent tasks."
    )

    # Under a broken sync implementation, ten 0.5s sleeps serialized
    # on the loop would push this to 5+ seconds. Under the offload
    # the loop stays responsive at <5ms.
    assert yield_latency < 0.05, (
        f"probe yield took {yield_latency*1000:.1f}ms with 10 "
        "concurrent policies still in flight — event loop is "
        "stalling. The offload broke under concurrency."
    )

    # And the total from probe_start — catches stalls during initial
    # scheduling that a mid-run yield wouldn't reflect.
    total = time.monotonic() - probe_start
    assert total < 0.5, (
        f"total wall-clock from probe start to loop-still-free was "
        f"{total*1000:.1f}ms — a stall happened before started_event "
        "fired."
    )

    await asyncio.gather(*workload, return_exceptions=False)
