"""X4 — v2 streaming lifetime invariants.

Before the fix, the coordinator's ``asyncio.wait_for`` only guarded
the header-arrival window. Once headers came back, wait_for stopped
enforcing the profile's ``timeout_seconds``. The handler then cancelled
the whole-request renewal task in its ``finally`` block BEFORE ASGI
consumed the stream body — meaning a legitimate long stream had its
audit lease revoked mid-flight, the reconciler flipped the row to
orphaned, and no wall-clock cap enforced total request duration.

Invariants this file locks:

- Wall-clock deadline: the wrapper raises ``TimeoutError`` if the
  stream body outlives the configured ``stream_deadline_seconds``, and
  finalize records ``execution_status='timeout'``.
- Renewal ownership transfer: the wrapper's ``finally`` cancels the
  ``durable.renewal_task`` AFTER finalize, not before. Otherwise the
  reconciler could see the row as expired in the gap.
- Handler skips ``_close_durable`` when a stream was wrapped —
  cancelling in both places would kill renewal before ASGI reads
  bytes.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import StreamingResponse


_HANDLER_SRC = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_handler.py"
).read_text(encoding="utf-8")


# ─── Wall-clock deadline enforcement ──────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_wrap_v2_stream_enforces_wall_clock_deadline(monkeypatch):
    """Body outlives ``stream_deadline_seconds`` → TimeoutError raised,
    finalize captures ``execution_status='timeout'``.

    Uses ``time.monotonic`` stubbing to drive the clock past the
    deadline between chunks so the test is deterministic.
    """
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    captured: dict = {}

    async def _fake_finalize(*, execution_status, decision, response_bytes, **_kw):
        captured.update(
            execution_status=execution_status,
            decision=decision,
            response_bytes=response_bytes,
        )

    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.finalize_durable_row",
        _fake_finalize,
    )
    async def _noop_close(_durable):
        return
    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.close_durable_row",
        _noop_close,
    )

    # Drive the clock: first check at t=0.0 (chunk 1 passes), second
    # check at t=100.0 (chunk 2 trips the 10s deadline). Then finalize
    # calls time.monotonic() for duration_ms — return 100.0 forever
    # after the second call.
    _tick_calls = {"n": 0}
    def _fake_time():
        _tick_calls["n"] += 1
        return 0.0 if _tick_calls["n"] < 2 else 100.0
    monkeypatch.setattr(
        "app.modules.guard.gateway_handler.time.monotonic",
        _fake_time,
    )

    async def _upstream():
        yield b"data: chunk-1\n\n"
        yield b"data: chunk-2\n\n"  # deadline trips before this yields
        yield b"data: [DONE]\n\n"

    inner = StreamingResponse(_upstream(), media_type="text/event-stream")
    wrapped = _wrap_v2_stream_finalize(
        inner,
        durable=None,
        row_id="row-1",
        workspace_id="ws",
        provider="anthropic",
        model="claude",
        body={},
        ingress_decision="allowed",
        ingress_rule_id=None,
        routing_meta={},
        clerk_user_id=None,
        ai_tool=None,
        user_email=None,
        started_monotonic=0.0,
        stream_deadline_seconds=10.0,
    )

    with pytest.raises(asyncio.TimeoutError):
        async for _ in wrapped.body_iterator:
            pass

    assert captured["execution_status"] == "timeout"
    assert captured["decision"] == "error"
    # Bytes from the first chunk survived; second never emitted.
    assert b"chunk-1" in (captured["response_bytes"] or b"")
    assert b"[DONE]" not in (captured["response_bytes"] or b"")


# ─── Renewal ownership transfer ───────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_wrap_v2_stream_cancels_renewal_after_finalize(monkeypatch):
    """The wrapper must cancel the durable renewal task AFTER finalize
    completes — otherwise the row could look expired to the reconciler
    between cancel and finalize."""
    from app.modules.guard.gateway_handler import _wrap_v2_stream_finalize

    call_order: list[str] = []

    async def _fake_finalize(**_kw):
        call_order.append("finalize")

    async def _fake_close(_durable):
        call_order.append("close_durable")

    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.finalize_durable_row",
        _fake_finalize,
    )
    monkeypatch.setattr(
        "app.modules.guard.gateway_lifecycle.close_durable_row",
        _fake_close,
    )

    async def _upstream():
        yield b"data: hi\n\n"

    inner = StreamingResponse(_upstream(), media_type="text/event-stream")
    fake_durable = MagicMock(name="DurableRow")
    wrapped = _wrap_v2_stream_finalize(
        inner,
        durable=fake_durable,
        row_id="row-1",
        workspace_id="ws",
        provider="anthropic",
        model="claude",
        body={},
        ingress_decision="allowed",
        ingress_rule_id=None,
        routing_meta={},
        clerk_user_id=None,
        ai_tool=None,
        user_email=None,
        started_monotonic=0.0,
    )
    async for _ in wrapped.body_iterator:
        pass

    assert call_order == ["finalize", "close_durable"], (
        f"wrapper must close durable AFTER finalize; got {call_order}"
    )


# ─── Handler wiring ───────────────────────────────────────────────────


def test_handler_transfers_renewal_ownership_to_stream_wrapper():
    """Source-level assertions locking the ownership-transfer wiring
    the handler now depends on.

    Regressions to catch:
    - If ``_v2_stream_wrapped`` disappears from the finally, we're
      back to cancelling renewal before the body is consumed.
    - If the wrapper stops taking ``durable`` and ``stream_deadline_seconds``
      the streaming path silently loses both lease renewal and
      wall-clock enforcement.
    """
    # Handler passes durable + deadline to the wrapper.
    assert "durable=_durable" in _HANDLER_SRC, (
        "handler must pass durable object into _wrap_v2_stream_finalize "
        "so the wrapper owns renewal cancellation"
    )
    assert "stream_deadline_seconds=" in _HANDLER_SRC, (
        "handler must pass a wall-clock deadline to the wrapper — "
        "coordinator's wait_for only guarded header arrival"
    )
    # Handler's finally skips close when the wrap took over.
    assert "if not _v2_stream_wrapped:" in _HANDLER_SRC, (
        "handler's finally must skip close_durable when a stream "
        "wrap transferred ownership; otherwise renewal ends before "
        "ASGI consumes the body"
    )


def test_wrapper_owns_close_durable_call():
    """The wrap's ``finally`` must call ``close_durable_row`` (or its
    aliased local import) so the renewal task actually gets cancelled
    somewhere. Combined with the handler guard above, this proves
    exactly one owner cancels the task."""
    from app.modules.guard import gateway_handler
    import inspect
    src = inspect.getsource(gateway_handler._wrap_v2_stream_finalize)
    assert "close_durable_row" in src, (
        "wrapper must reference close_durable_row so renewal is "
        "cancelled after finalize completes"
    )
