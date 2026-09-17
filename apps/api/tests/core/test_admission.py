"""Admission control tests — unit + endpoint-integration.

Uses deliberately small caps (workspace_max=1, global_max=2) so overlap
is provable with a small handful of concurrent requests.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import patch

import pytest

# Force admission ON for the duration of these tests. The module reads the
# env var at ``configure_defaults()`` call time.
os.environ["ADMISSION_ENABLED"] = "true"

from app.core.admission import (  # noqa: E402
    AdmissionRefused,
    Ticket,
    _STATE,
    _acquire,
    admit,
    configure_defaults,
    stats,
)


def _reset_state(surface: str, *, global_max: int, workspace_max: int) -> None:
    """Wipe and re-seed a surface's counters. Idempotent per test."""
    _STATE.pop(surface, None)
    from app.core.admission import _SurfaceState
    _STATE[surface] = _SurfaceState(global_max=global_max, workspace_max=workspace_max)


# ── Unit tests: admit() context manager ────────────────────────────────

@pytest.mark.asyncio
async def test_admit_workspace_cap_rejects_second_concurrent():
    """Workspace cap = 1 → second concurrent from same workspace = 429."""
    _reset_state("gateway", global_max=10, workspace_max=1)

    holding = asyncio.Event()
    release = asyncio.Event()

    async def _hold():
        async with admit("gateway", "ws-a"):
            holding.set()
            await release.wait()

    task = asyncio.create_task(_hold())
    await holding.wait()  # ensure first request has the slot

    with pytest.raises(AdmissionRefused) as excinfo:
        async with admit("gateway", "ws-a"):
            pass
    assert excinfo.value.http_status == 429
    assert excinfo.value.scope == "workspace"

    release.set()
    await task
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_global_cap_rejects_third_concurrent_across_workspaces():
    """Global cap = 2 with lifted workspace cap → third acquire = 503."""
    _reset_state("gateway", global_max=2, workspace_max=10)

    holding = asyncio.Event()
    release = asyncio.Event()
    holds = 0

    async def _hold(ws):
        nonlocal holds
        async with admit("gateway", ws):
            holds += 1
            if holds == 2:
                holding.set()
            await release.wait()

    t1 = asyncio.create_task(_hold("ws-a"))
    t2 = asyncio.create_task(_hold("ws-b"))
    await holding.wait()

    with pytest.raises(AdmissionRefused) as excinfo:
        async with admit("gateway", "ws-c"):
            pass
    assert excinfo.value.http_status == 503
    assert excinfo.value.scope == "global"

    release.set()
    await asyncio.gather(t1, t2)
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_workspace_check_happens_before_global():
    """Workspace-throttled request never holds a global counter."""
    _reset_state("gateway", global_max=10, workspace_max=1)

    holding = asyncio.Event()
    release = asyncio.Event()

    async def _hold():
        async with admit("gateway", "ws-a"):
            holding.set()
            await release.wait()

    task = asyncio.create_task(_hold())
    await holding.wait()

    inflight_before = _STATE["gateway"].global_inflight

    with pytest.raises(AdmissionRefused) as excinfo:
        async with admit("gateway", "ws-a"):
            pass
    assert excinfo.value.scope == "workspace"

    # Global counter is unchanged — workspace check ran first.
    assert _STATE["gateway"].global_inflight == inflight_before

    release.set()
    await task


@pytest.mark.asyncio
async def test_admit_cancellation_releases_slot():
    """Cancelling a task holding a slot releases both counters."""
    _reset_state("gateway", global_max=2, workspace_max=1)

    async def _hang():
        async with admit("gateway", "ws-x"):
            await asyncio.sleep(10)

    task = asyncio.create_task(_hang())
    await asyncio.sleep(0.01)
    assert _STATE["gateway"].global_inflight == 1

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _STATE["gateway"].global_inflight == 0
    assert _STATE["gateway"].workspace_inflight.get("ws-x", 0) == 0


@pytest.mark.asyncio
async def test_admit_after_release_next_request_succeeds():
    """After first request releases, a fresh request from the same workspace succeeds."""
    _reset_state("gateway", global_max=2, workspace_max=1)

    async with admit("gateway", "ws-y"):
        pass
    assert _STATE["gateway"].global_inflight == 0

    async with admit("gateway", "ws-y"):
        assert _STATE["gateway"].global_inflight == 1
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_deferred_release_for_streaming():
    """ticket.defer() prevents auto-release; caller must call release()."""
    _reset_state("gateway", global_max=2, workspace_max=1)

    ticket_ref: Ticket | None = None
    async with admit("gateway", "ws-z") as t:
        t.defer()
        ticket_ref = t
        assert _STATE["gateway"].global_inflight == 1
    # Context exited but slot still held.
    assert _STATE["gateway"].global_inflight == 1
    await ticket_ref.release()
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_rejects_empty_workspace_id():
    """Empty workspace_id must never be accepted — defense against client-supplied ID."""
    _reset_state("gateway", global_max=2, workspace_max=1)
    with pytest.raises(ValueError):
        async with admit("gateway", ""):
            pass


@pytest.mark.asyncio
async def test_admit_passthrough_when_not_configured():
    """When a surface has no state (kill switch off), admit is a no-op."""
    _STATE.pop("gateway", None)
    async with admit("gateway", "ws-any"):
        pass


# ── Integration tests: /mcp endpoint under overlap ────────────────────

@pytest.fixture
def mcp_client(monkeypatch):
    """FastAPI TestClient with a mocked-out MCPContext resolver so the
    endpoint doesn't require a real DB or Clerk. Also caps admission
    to workspace_max=1, global_max=2 to prove overlap protection."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.mcp import http as mcp_http

    _reset_state("mcp", global_max=2, workspace_max=1)

    # Bypass real auth: any request with "Authorization: Bearer test" gets
    # the same workspace_id back. Overlap tests use the same ws → workspace
    # cap trips; cross-ws tests set different tokens.
    def _fake_auth(request):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"error": "no bearer"})
        token = auth[7:]
        return (f"ws-{token}", "user-1")

    monkeypatch.setattr(mcp_http, "_auth_or_401", _fake_auth)
    monkeypatch.setattr(mcp_http, "_extract_bearer", lambda r: "bearer")
    monkeypatch.setattr(mcp_http, "new_session_id", lambda: "sess-1")

    # Slow dispatch so overlapping requests actually overlap in time.
    def _slow_dispatch(body, ctx, registry):
        import time as _time
        _time.sleep(0.15)  # runs in threadpool, doesn't block loop
        return {"jsonrpc": "2.0", "id": body.get("id"), "result": {"ok": True}}

    monkeypatch.setattr(mcp_http, "dispatch", _slow_dispatch)

    # Skip Clerk email lookup.
    monkeypatch.setattr(
        "app.core.auth.get_clerk_user_email",
        lambda _uid: "test@example.com",
    )

    app = FastAPI()
    app.include_router(mcp_http.router)
    return TestClient(app)


def _fire_concurrent_mcp(client, n, token="a"):
    """Fire n concurrent /mcp POSTs. Returns list of status codes."""
    import threading

    results: list[int] = []
    lock = threading.Lock()

    def _one(i):
        r = client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {token}"},
            json={"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {}},
        )
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=_one, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_mcp_endpoint_workspace_cap_rejects_overlap(mcp_client):
    """3 concurrent /mcp requests, same workspace, cap=1 → 1 pass, 2 × 429."""
    codes = _fire_concurrent_mcp(mcp_client, 3, token="a")
    assert codes.count(200) >= 1, f"expected ≥1 200s, got {codes}"
    assert codes.count(429) >= 1, f"expected ≥1 429s, got {codes}"


def test_mcp_endpoint_global_cap_rejects_overlap_across_workspaces(mcp_client):
    """Bump workspace_max, keep global_max=2 → 4 requests across 4 ws hits 503."""
    _reset_state("mcp", global_max=2, workspace_max=10)

    import threading

    results: list[int] = []
    lock = threading.Lock()

    def _one(i):
        r = mcp_client.post(
            "/mcp",
            headers={"Authorization": f"Bearer {i}"},
            json={"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {}},
        )
        with lock:
            results.append(r.status_code)

    threads = [threading.Thread(target=_one, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count(503) >= 1, f"expected ≥1 503s, got {results}"


def test_mcp_endpoint_slot_recovers_after_release(mcp_client):
    """Fire cap+1 concurrent, wait, then a fresh request succeeds."""
    _fire_concurrent_mcp(mcp_client, 2, token="a")

    r = mcp_client.post(
        "/mcp",
        headers={"Authorization": "Bearer a"},
        json={"jsonrpc": "2.0", "id": 999, "method": "tools/call", "params": {}},
    )
    assert r.status_code == 200


def test_mcp_endpoint_retry_after_header(mcp_client):
    """429/503 responses carry a Retry-After header."""
    import threading

    codes_and_headers: list[tuple[int, str | None]] = []
    lock = threading.Lock()

    def _one(i):
        r = mcp_client.post(
            "/mcp",
            headers={"Authorization": "Bearer a"},
            json={"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {}},
        )
        with lock:
            codes_and_headers.append((r.status_code, r.headers.get("Retry-After")))

    threads = [threading.Thread(target=_one, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    refused = [(c, h) for c, h in codes_and_headers if c == 429]
    assert refused, "expected at least one 429"
    for _, header in refused:
        assert header is not None, "429 must carry Retry-After"


# ── Regression: bugs surfaced in PR 2 review ──────────────────────────

@pytest.mark.asyncio
async def test_admit_releases_slot_when_body_raises_after_acquire():
    """P1 fix: any exception AFTER admission acquire — including during the
    'gap' code path where durable acceptance fires — releases the slot.

    Reviewer reproducer: audit-outage returned 503 but global_inflight
    stayed at 1. This test exercises the same shape at the primitive
    layer: exception mid-body → outer finally must release."""
    _reset_state("gateway", global_max=2, workspace_max=1)

    class _FakeAuditFailure(Exception):
        pass

    with pytest.raises(_FakeAuditFailure):
        async with admit("gateway", "ws-audit"):
            # Simulate durable-acceptance failure between DB block and upstream try.
            raise _FakeAuditFailure("audit write failed")

    assert _STATE["gateway"].global_inflight == 0, "slot leaked on mid-body exception"
    assert _STATE["gateway"].workspace_inflight.get("ws-audit", 0) == 0


@pytest.mark.asyncio
async def test_admit_repeated_audit_failure_does_not_exhaust_admission():
    """P1 fix: repeated failure-during-body must not exhaust the pool."""
    _reset_state("gateway", global_max=1, workspace_max=1)

    for _ in range(5):
        try:
            async with admit("gateway", "ws-loop"):
                raise RuntimeError("simulated audit failure")
        except RuntimeError:
            pass

    assert _STATE["gateway"].global_inflight == 0
    # Fresh acquire must succeed — pool not exhausted.
    async with admit("gateway", "ws-loop"):
        assert _STATE["gateway"].global_inflight == 1
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_deferred_release_holds_slot_until_explicit_release():
    """P1 fix (streaming): with ticket.defer() the slot is held past
    context exit — mirroring the pattern where release is transferred to
    the stream lifecycle. Verifies the slot IS held throughout the
    'stream duration' and released only when the caller triggers it."""
    _reset_state("gateway", global_max=2, workspace_max=1)

    ticket_holder: list[Ticket] = []
    async with admit("gateway", "ws-stream") as t:
        t.defer()
        ticket_holder.append(t)
        assert _STATE["gateway"].global_inflight == 1

    # Context exited — but slot STILL held (deferred).
    assert _STATE["gateway"].global_inflight == 1

    # A concurrent request from the same workspace is rejected because
    # the deferred slot is still occupied.
    with pytest.raises(AdmissionRefused) as excinfo:
        async with admit("gateway", "ws-stream"):
            pass
    assert excinfo.value.scope == "workspace"

    # Simulate stream close → callback fires release.
    await ticket_holder[0].release()
    assert _STATE["gateway"].global_inflight == 0

    # Now a fresh acquire succeeds.
    async with admit("gateway", "ws-stream"):
        pass
    assert _STATE["gateway"].global_inflight == 0


@pytest.mark.asyncio
async def test_admit_release_is_idempotent_after_double_call():
    """P1 fix: on_close in stream wrap + outer finally can both fire.
    release() must be idempotent so double-fire doesn't underflow."""
    _reset_state("gateway", global_max=2, workspace_max=2)

    async with admit("gateway", "ws-idem") as t:
        t.defer()
        await t.release()
        await t.release()  # idempotent — no double-decrement
        await t.release()

    assert _STATE["gateway"].global_inflight == 0


def test_admission_refused_carries_retry_after():
    """P2 fix: AdmissionRefused exposes retry_after_seconds so the caller
    can set the Retry-After HTTP header. gateway_handler now builds a
    JSONResponse with this header for 429/503 admission refusals."""
    exc_workspace = AdmissionRefused(
        http_status=429, scope="workspace", retry_after_seconds=1.0
    )
    exc_global = AdmissionRefused(
        http_status=503, scope="global", retry_after_seconds=2.0
    )
    assert exc_workspace.retry_after_seconds == 1.0
    assert exc_global.retry_after_seconds == 2.0
    assert exc_workspace.http_status == 429
    assert exc_global.http_status == 503


# ── Stats snapshot ────────────────────────────────────────────────────

def test_stats_returns_counters():
    _reset_state("gateway", global_max=3, workspace_max=2)
    st = stats("gateway")
    assert st["global_max"] == 3
    assert st["workspace_max"] == 2
    assert st["global_inflight"] == 0
