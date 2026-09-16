"""X2 — v2 audit fallback when durable-audit is off.

Locks the invariant that v2 traffic ALWAYS lands an audit row, even
when the workspace hasn't opted into durable audit yet. Before the
fix, v2 requests skipped both the durable-audit finalize path
(gated on ``_durable_row_id``) and v1's legacy ``_record_audit``
(never called because we're on the v2 branch), leaving a silent gap
in the audit table during the canary ramp.

Scope: the wrap that handles the streaming fallback path. The
non-streaming inline branch is simple enough to verify by source
inspection — an assertion here would either mock the whole
gateway_handler or fire a real request through Redis + Vault + RLS.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.responses import StreamingResponse


@pytest.mark.anyio("asyncio")
async def test_stream_record_legacy_fires_record_audit_on_close():
    """Stream drains successfully → BackgroundTasks receives a
    ``_record_audit`` call with the collected bytes and
    execution_status='success' (v1's ok status string)."""
    from app.modules.guard.gateway_handler import _wrap_v2_stream_record_legacy

    async def _upstream():
        yield b"data: chunk-1\n\n"
        yield b"data: chunk-2\n\n"
        yield b"data: [DONE]\n\n"

    inner = StreamingResponse(_upstream(), media_type="text/event-stream")

    # BackgroundTasks stub — capture the (fn, args, kwargs) it's asked
    # to schedule.
    scheduled: list[tuple] = []
    background = MagicMock()
    background.add_task = lambda fn, *args, **kwargs: scheduled.append(
        (fn, args, kwargs)
    )

    record_stub = MagicMock(name="_record_audit")

    wrapped = _wrap_v2_stream_record_legacy(
        inner,
        background=background,
        workspace_id="ws-1",
        clerk_user_id="u-1",
        ai_tool="cursor",
        provider="anthropic",
        model="claude-sonnet",
        body={"messages": []},
        prompt_summary="hi",
        user_email="a@b.co",
        conductai_run_id=None,
        conductai_workflow=None,
        conductai_workflow_id=None,
        hook_session_id=None,
        routing_meta={"gateway_version": "v2"},
        agent_identity_id=None,
        route="/gateway/v1/anthropic/v1/messages",
        ingress_decision="allowed",
        ingress_rule_id=None,
        started_monotonic=0.0,
        record_audit_fn=record_stub,
    )

    async for _ in wrapped.body_iterator:
        pass

    assert len(scheduled) == 1, scheduled
    fn, args, kwargs = scheduled[0]
    assert fn is record_stub
    # Positional args: workspace_id, clerk_user_id, ai_tool, provider,
    # model, decision, rule_id, duration_ms.
    assert args[0] == "ws-1"
    assert args[1] == "u-1"
    assert args[2] == "cursor"
    assert args[3] == "anthropic"
    assert args[4] == "claude-sonnet"
    assert args[5] == "allowed"
    assert args[6] is None
    # Kwargs: execution_status='success', bytes collected end-to-end.
    assert kwargs["execution_status"] == "success"
    assert b"[DONE]" in kwargs["response_bytes"]
    assert b"chunk-1" in kwargs["response_bytes"]


@pytest.mark.anyio("asyncio")
async def test_stream_record_legacy_maps_cancel_to_interrupted():
    """Stream cancellation → execution_status='interrupted' (matches
    v1's ``_stream_chunks`` on CancelledError). Distinguishes an
    aborted stream from a genuine upstream failure in dashboards."""
    import asyncio

    from app.modules.guard.gateway_handler import _wrap_v2_stream_record_legacy

    async def _upstream():
        yield b"data: partial\n\n"
        raise asyncio.CancelledError()

    inner = StreamingResponse(_upstream(), media_type="text/event-stream")

    captured: dict = {}
    background = MagicMock()
    background.add_task = lambda fn, *args, **kwargs: captured.update(kwargs=kwargs, args=args)

    wrapped = _wrap_v2_stream_record_legacy(
        inner,
        background=background,
        workspace_id="ws-1",
        clerk_user_id="u-1",
        ai_tool="cursor",
        provider="anthropic",
        model="claude-sonnet",
        body={},
        prompt_summary="",
        user_email=None,
        conductai_run_id=None,
        conductai_workflow=None,
        conductai_workflow_id=None,
        hook_session_id=None,
        routing_meta={},
        agent_identity_id=None,
        route="/x",
        ingress_decision="allowed",
        ingress_rule_id=None,
        started_monotonic=0.0,
        record_audit_fn=MagicMock(),
    )

    with pytest.raises(asyncio.CancelledError):
        async for _ in wrapped.body_iterator:
            pass

    assert captured["kwargs"]["execution_status"] == "interrupted"
    # Decision must reflect the failure, not the ingress "allowed".
    # First positional arg after workspace_id/clerk_user_id/ai_tool/
    # provider/model is decision.
    assert captured["args"][5] == "error"


def test_handler_wires_fallback_branch_when_durable_row_absent():
    """Source-level assertion: gateway_handler routes to the legacy
    fallback wrapper when v2 is on but durable-audit is off. Catches
    a future edit that would re-introduce the silent audit gap."""
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "guard" / "gateway_handler.py"
    ).read_text(encoding="utf-8")
    # Look for both branches within the v2 finalize block.
    assert "if _v2_plan is not None and _durable_row_id:" in src
    assert "elif _v2_plan is not None:" in src, (
        "gateway_handler must fall through to legacy _record_audit "
        "when v2 executed but durable-audit was off. Without this "
        "elif, v2 traffic silently skips audit."
    )
    assert "_wrap_v2_stream_record_legacy" in src


def test_handler_records_audit_on_exception_when_durable_off():
    """Y2 REPRODUCER — the initial X2 fix only handled happy-path
    returns. If the coordinator raised (network error, all-attempts-
    failed, cancellation), the exception handler only recorded when
    a durable row existed. With durable-audit off, exception-path v2
    requests wrote zero rows.

    Source-level regression guard: the except block must also schedule
    ``_record_audit`` in the ``elif _v2_plan is not None:`` shape.
    """
    from pathlib import Path
    src = (
        Path(__file__).resolve().parents[2]
        / "app" / "modules" / "guard" / "gateway_handler.py"
    ).read_text(encoding="utf-8")

    # Find the exception handler section.
    exc_start = src.index("except BaseException as _forward_exc")
    exc_end = src.index("finally:", exc_start)
    exc_block = src[exc_start:exc_end]

    # It must contain BOTH the durable finalize AND a v2 record-audit
    # fallback — otherwise durable-off exception paths land no row.
    assert "if _durable_row_id:" in exc_block, (
        "exception handler must still finalize the durable row when "
        "one exists"
    )
    assert "elif _v2_plan is not None:" in exc_block, (
        "exception handler must schedule _record_audit for v2 when "
        "durable-audit was off — otherwise error rows are invisible"
    )
    # Must actually reference _record_audit + background.add_task in
    # the exception block, not just the happy-path branch above.
    assert "_record_audit" in exc_block
    assert "background.add_task" in exc_block
