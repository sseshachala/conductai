"""Local admission control for gateway + MCP hot paths.

Reject-first, no queue. On overload:
  - workspace slot full → AdmissionRefused(429)  (per-tenant throttle)
  - global slot full    → AdmissionRefused(503)  (service-wide saturation)

Invariants (from #2057):
  - workspace_id MUST come from resolved auth, never client input
  - workspace slot is acquired before global slot; a workspace-throttled
    request never holds a global counter
  - slot is held for the entire context lifetime including any streaming
    response yielded from within — caller defers release via Ticket.defer()
    and attaches Ticket.release to StreamingResponse.background
  - cancellation, exceptions, and normal exit all release both counters
    exactly once
  - dropped-workspace entries GC out on an idle sweep so the counter dict
    does not grow unboundedly

Explicit non-claim: process-local. A 4-worker deployment with
workspace_max=25 admits up to 100 requests per workspace instance-wide.
Full cross-worker isolation requires a Redis-backed shared counter
(deferred; see #2057 Stage 4).
"""
from __future__ import annotations

import asyncio
import os
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import AsyncIterator, Literal

import structlog

log = structlog.get_logger()

Surface = Literal["gateway", "mcp"]


class AdmissionRefused(Exception):
    """Raised when admission is denied. Handler translates to HTTP status."""

    def __init__(self, *, http_status: int, scope: str, retry_after_seconds: float):
        self.http_status = http_status
        self.scope = scope
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"admission refused: {scope} slot full")


@dataclass
class _SurfaceState:
    global_max: int
    workspace_max: int
    global_inflight: int = 0
    workspace_inflight: dict[str, int] = field(default_factory=dict)
    last_activity: dict[str, float] = field(default_factory=dict)
    # ``threading.Lock`` not ``asyncio.Lock`` so this state works across event
    # loops (multi-worker FastAPI, TestClient thread pools). The critical
    # section is a handful of dict ops — no awaits inside.
    lock: threading.Lock = field(default_factory=threading.Lock)
    admitted_total: int = 0
    refused_workspace_total: int = 0
    refused_global_total: int = 0


_STATE: dict[str, _SurfaceState] = {}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _admission_enabled() -> bool:
    """Kill switch. Default OFF — deploy the code, flip the env var to turn on."""
    return os.environ.get("ADMISSION_ENABLED", "false").lower() in ("1", "true", "yes")


def configure_defaults() -> None:
    """Populate per-surface caps from env with sane defaults. Idempotent.

    Skips entirely when ``ADMISSION_ENABLED`` is not truthy — leaving
    ``_STATE`` empty so ``admit()`` becomes a no-op pass-through.

    Caps are process-local. A 4-worker deployment with
    ``workspace_max=25`` admits up to ``4 x 25 = 100`` concurrent requests
    per workspace instance-wide (per-worker × worker count). For
    validation, use small caps (workspace_max=2, global_max=4) so
    overlap is provable with a handful of concurrent requests. The
    default caps here are placeholders to tune post-canary — use the
    stress-test at ``scripts/stress_gateway.py`` to right-size them.
    """
    if not _admission_enabled():
        return
    if "gateway" not in _STATE:
        _STATE["gateway"] = _SurfaceState(
            global_max=_env_int("GATEWAY_ADMISSION_MAX_INFLIGHT", 50),
            workspace_max=_env_int("GATEWAY_ADMISSION_WORKSPACE_MAX", 25),
        )
    if "mcp" not in _STATE:
        _STATE["mcp"] = _SurfaceState(
            global_max=_env_int("MCP_ADMISSION_MAX_INFLIGHT", 50),
            workspace_max=_env_int("MCP_ADMISSION_WORKSPACE_MAX", 25),
        )


class Ticket:
    """Handle to a claimed admission slot. Release exactly once."""

    __slots__ = ("_surface", "_workspace_id", "_released", "_deferred")

    def __init__(self, surface: Surface, workspace_id: str):
        self._surface = surface
        self._workspace_id = workspace_id
        self._released = False
        self._deferred = False

    @property
    def released(self) -> bool:
        return self._released

    def defer(self) -> None:
        """Mark the slot as caller-owned. Context manager will not auto-release.

        Use before returning a StreamingResponse and attach ``release`` to
        ``response.background`` so the slot releases when the stream ends.
        """
        self._deferred = True

    async def release(self) -> None:
        if self._released:
            return
        self._released = True
        st = _STATE.get(self._surface)
        if st is None:
            return
        with st.lock:
            ws_current = st.workspace_inflight.get(self._workspace_id, 0)
            if ws_current > 0:
                st.workspace_inflight[self._workspace_id] = ws_current - 1
            if st.global_inflight > 0:
                st.global_inflight -= 1
            st.last_activity[self._workspace_id] = time.monotonic()


async def _acquire(surface: Surface, workspace_id: str) -> Ticket:
    st = _STATE.get(surface)
    if st is None:
        # Admission not configured — pass through (opt-in per surface).
        return Ticket(surface, workspace_id)
    with st.lock:
        ws_current = st.workspace_inflight.get(workspace_id, 0)
        if ws_current >= st.workspace_max:
            st.refused_workspace_total += 1
            _refused = AdmissionRefused(
                http_status=429,
                scope="workspace",
                retry_after_seconds=1.0,
            )
            _cap = st.workspace_max
        elif st.global_inflight >= st.global_max:
            st.refused_global_total += 1
            _refused = AdmissionRefused(
                http_status=503,
                scope="global",
                retry_after_seconds=2.0,
            )
            _cap = st.global_max
        else:
            _refused = None
            st.workspace_inflight[workspace_id] = ws_current + 1
            st.global_inflight += 1
            st.last_activity[workspace_id] = time.monotonic()
            st.admitted_total += 1
    if _refused is not None:
        log.info(
            "admission.refused",
            surface=surface,
            scope=_refused.scope,
            workspace_id=workspace_id,
            cap=_cap,
        )
        raise _refused
    return Ticket(surface, workspace_id)


@asynccontextmanager
async def admit(surface: Surface, workspace_id: str) -> AsyncIterator[Ticket]:
    """Reject-first admission. Yields a Ticket.

    Non-streaming caller: context exit auto-releases.
    Streaming caller: ``ticket.defer()`` then attach ``ticket.release`` to
    ``StreamingResponse.background`` so the slot releases on stream close.
    """
    if not workspace_id:
        raise ValueError("admit() requires resolved workspace_id, not client input")
    ticket = await _acquire(surface, workspace_id)
    try:
        yield ticket
    except BaseException:
        # Cancellation / exception / HTTPException — release always.
        await ticket.release()
        raise
    else:
        if not ticket._deferred:
            await ticket.release()


async def _gc_loop(interval_seconds: float = 30.0, idle_seconds: float = 60.0) -> None:
    """Evict workspace entries at 0 inflight and idle > idle_seconds."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = time.monotonic()
            for surface, st in list(_STATE.items()):
                with st.lock:
                    to_evict = [
                        ws
                        for ws, count in st.workspace_inflight.items()
                        if count == 0
                        and (now - st.last_activity.get(ws, 0.0)) > idle_seconds
                    ]
                    for ws in to_evict:
                        st.workspace_inflight.pop(ws, None)
                        st.last_activity.pop(ws, None)
                if to_evict:
                    log.debug(
                        "admission.gc",
                        surface=surface,
                        evicted=len(to_evict),
                    )
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("admission.gc_error", err=str(e))


async def _loop_lag_sampler(sample_interval: float = 5.0) -> None:
    """Sample event-loop lag per worker. One task per worker, not per request."""
    while True:
        try:
            t0 = time.monotonic()
            await asyncio.sleep(sample_interval)
            actual = time.monotonic() - t0
            lag_ms = max(0.0, (actual - sample_interval) * 1000.0)
            if lag_ms > 100.0:
                log.warning("admission.loop_lag_high", lag_ms=round(lag_ms, 1))
            else:
                log.debug("admission.loop_lag", lag_ms=round(lag_ms, 1))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.warning("admission.loop_lag_error", err=str(e))


_background_tasks: list[asyncio.Task] = []


def start_background_tasks() -> None:
    """Called from FastAPI startup. Idempotent."""
    if _background_tasks:
        return
    configure_defaults()
    loop = asyncio.get_event_loop()
    _background_tasks.append(loop.create_task(_gc_loop(), name="admission.gc"))
    _background_tasks.append(
        loop.create_task(_loop_lag_sampler(), name="admission.loop_lag")
    )


def admission_refused_jsonrpc(msg_id, exc: AdmissionRefused):
    """Shared JSON-RPC error envelope for MCP admission refusal.

    Imported locally where needed so this module stays free of framework deps
    for its self-check. Returns a starlette JSONResponse.
    """
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=exc.http_status,
        content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {
                "code": -32000,
                "message": f"MCP overloaded ({exc.scope} slot full) — retry after {int(exc.retry_after_seconds)}s",
            },
        },
        headers={"Retry-After": str(int(exc.retry_after_seconds))},
    )


def stats(surface: Surface) -> dict:
    """Snapshot of counters for the given surface. Debug/health endpoint."""
    st = _STATE.get(surface)
    if st is None:
        return {}
    return {
        "global_inflight": st.global_inflight,
        "global_max": st.global_max,
        "workspace_max": st.workspace_max,
        "workspace_count": len(st.workspace_inflight),
        "admitted_total": st.admitted_total,
        "refused_workspace_total": st.refused_workspace_total,
        "refused_global_total": st.refused_global_total,
    }


# Self-check: `python -m app.core.admission`
if __name__ == "__main__":
    import asyncio as _asyncio

    async def _self_check():
        configure_defaults()
        # Override for the test.
        _STATE["gateway"].global_max = 2
        _STATE["gateway"].workspace_max = 1

        # 1) Acquire and release within a context works.
        async with admit("gateway", "ws-a") as t:
            assert not t.released
        assert _STATE["gateway"].global_inflight == 0, "should release on exit"

        # 2) Workspace cap = 1 → second concurrent acquire from same workspace = 429.
        async def _hold():
            async with admit("gateway", "ws-a"):
                await _asyncio.sleep(0.05)

        h = _asyncio.create_task(_hold())
        await _asyncio.sleep(0.01)  # let h acquire
        try:
            async with admit("gateway", "ws-a"):
                assert False, "expected AdmissionRefused (workspace)"
        except AdmissionRefused as e:
            assert e.http_status == 429 and e.scope == "workspace"
        await h

        # 3) Global cap = 2 with workspace_max lifted → third acquire = 503.
        _STATE["gateway"].workspace_max = 10
        h1 = _asyncio.create_task(_hold())
        h2 = _asyncio.create_task(_asyncio.sleep(0))
        async def _hold_b():
            async with admit("gateway", "ws-b"):
                await _asyncio.sleep(0.05)
        h_b = _asyncio.create_task(_hold_b())
        await _asyncio.sleep(0.01)
        try:
            async with admit("gateway", "ws-c"):
                assert False, "expected AdmissionRefused (global)"
        except AdmissionRefused as e:
            assert e.http_status == 503 and e.scope == "global"
        await _asyncio.gather(h1, h_b, h2)

        # 4) Cancellation releases the slot.
        _STATE["gateway"].workspace_max = 1
        _STATE["gateway"].global_max = 2

        async def _cancelable():
            async with admit("gateway", "ws-x"):
                await _asyncio.sleep(1)

        task = _asyncio.create_task(_cancelable())
        await _asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except _asyncio.CancelledError:
            pass
        assert _STATE["gateway"].workspace_inflight.get("ws-x", 0) == 0
        assert _STATE["gateway"].global_inflight == 0

        # 5) Deferred release for streaming.
        async with admit("gateway", "ws-y") as t:
            t.defer()
            assert _STATE["gateway"].global_inflight == 1
        # Not released yet — deferred.
        assert _STATE["gateway"].global_inflight == 1
        await t.release()
        assert _STATE["gateway"].global_inflight == 0

        # 6) Empty workspace_id rejected.
        try:
            async with admit("gateway", ""):
                assert False, "expected ValueError on empty workspace_id"
        except ValueError:
            pass

        print("admission self-check: OK")

    _asyncio.run(_self_check())
