"""#1733 PR 5 — response gate on streaming path (buffered end-of-stream scan).

ponytail: buffered — client already saw chunks by the time we decide. This
suite proves telemetry (server-side WARN) fires on block. The chunk-scan
upgrade path (mid-stream halt) is a follow-on.

ponytail: async tests wrapped in asyncio.run() rather than marking with
pytest.mark.asyncio so we don't add pytest-asyncio as a CI dep for four
tests.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch

from fastapi.responses import StreamingResponse

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.modules.guard.routers.proxy import (
    _extract_stream_text,
    _wrap_streaming_response,
)


def test_extract_stream_text_from_anthropic_deltas():
    sse = (
        b'event: content_block_delta\n'
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello "}}\n\n'
        b'event: content_block_delta\n'
        b'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"world"}}\n\n'
    )
    text = _extract_stream_text(sse)
    assert "Hello " in text
    assert "world" in text


def test_extract_stream_text_from_openai_deltas():
    sse = (
        b'data: {"choices":[{"delta":{"content":"Hello "}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":"world"}}]}\n\n'
        b'data: [DONE]\n\n'
    )
    text = _extract_stream_text(sse)
    assert "Hello " in text
    assert "world" in text


def test_extract_stream_text_handles_escaped_quotes():
    """Regex must handle escape sequences without truncating text."""
    sse = b'data: {"delta":{"text":"quoted \\"foo\\" bar"}}\n\n'
    text = _extract_stream_text(sse)
    assert 'quoted "foo" bar' in text


async def _drain(response: StreamingResponse) -> bytes:
    out = bytearray()
    async for chunk in response.body_iterator:
        out.extend(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
    return bytes(out)


def test_wrap_streaming_response_passes_chunks_through_unchanged():
    """Chunks reach the client verbatim — buffered scan happens at end only."""
    async def _body():
        async def _fake_stream():
            yield b'data: {"delta":{"text":"hello"}}\n\n'
            yield b'data: {"delta":{"text":" world"}}\n\n'

        inner = StreamingResponse(_fake_stream(), media_type="text/event-stream")
        with patch(
            "app.modules.guard.routers.proxy._evaluate_response_body",
            return_value=PolicyDecision(action=PolicyAction.ALLOW, source="rule"),
        ):
            wrapped = _wrap_streaming_response(
                inner, workspace_id="ws-a", provider="anthropic", model="claude-3",
                clerk_user_id="u1", agent_identity_id=None,
            )
            return await _drain(wrapped)

    drained = asyncio.run(_body())
    assert b'"text":"hello"' in drained
    assert b'"text":" world"' in drained


def test_wrap_streaming_response_evaluates_synthetic_response_body():
    """After the stream drains, the evaluator sees a body with text extracted
    from every text/content delta — Anthropic-shape synthetic envelope."""
    seen = {}

    async def _body():
        async def _fake_stream():
            yield b'data: {"delta":{"text":"leak-me-if-you-can"}}\n\n'

        inner = StreamingResponse(_fake_stream(), media_type="text/event-stream")

        def _spy(resp_body, **kwargs):
            seen["body"] = resp_body
            return PolicyDecision(action=PolicyAction.ALLOW, source="rule")

        with patch(
            "app.modules.guard.routers.proxy._evaluate_response_body",
            side_effect=_spy,
        ):
            wrapped = _wrap_streaming_response(
                inner, workspace_id="ws-a", provider="anthropic", model="claude-3",
                clerk_user_id="u1", agent_identity_id=None,
            )
            await _drain(wrapped)

    asyncio.run(_body())
    assert seen["body"]["content"][0]["text"] == "leak-me-if-you-can"


def test_wrap_streaming_response_logs_when_block_fires_post_hoc():
    """structlog doesn't route through stdlib caplog — patch log.warning
    directly to capture the response-gate telemetry payload."""
    calls = []

    async def _body():
        async def _fake_stream():
            yield b'data: {"delta":{"text":"SSN 123-45-6789"}}\n\n'

        inner = StreamingResponse(_fake_stream(), media_type="text/event-stream")
        block = PolicyDecision(
            action=PolicyAction.BLOCK, source="rule",
            reason="SSN leaked in stream", rule_id="hipaa-no-ssn-out",
        )
        with patch(
            "app.modules.guard.routers.proxy._evaluate_response_body",
            return_value=block,
        ), patch(
            "app.modules.guard.routers.proxy.log.warning",
            side_effect=lambda event, **kw: calls.append((event, kw)),
        ):
            wrapped = _wrap_streaming_response(
                inner, workspace_id="ws-a", provider="anthropic", model="claude-3",
                clerk_user_id="u1", agent_identity_id=None,
            )
            await _drain(wrapped)

    asyncio.run(_body())
    events = [c[0] for c in calls]
    assert "guard.proxy.response_stream_blocked_post_hoc" in events
    payload = next(kw for ev, kw in calls if ev == "guard.proxy.response_stream_blocked_post_hoc")
    assert payload["rule_id"] == "hipaa-no-ssn-out"
    assert payload["workspace_id"] == "ws-a"


def test_wrap_streaming_response_swallows_evaluator_errors():
    """Even a policy engine crash must not corrupt the response stream."""
    async def _body():
        async def _fake_stream():
            yield b'data: {"delta":{"text":"hi"}}\n\n'

        inner = StreamingResponse(_fake_stream(), media_type="text/event-stream")
        with patch(
            "app.modules.guard.routers.proxy._evaluate_response_body",
            side_effect=RuntimeError("engine down"),
        ):
            wrapped = _wrap_streaming_response(
                inner, workspace_id="ws-a", provider="anthropic", model="claude-3",
                clerk_user_id="u1", agent_identity_id=None,
            )
            return await _drain(wrapped)

    drained = asyncio.run(_body())
    assert b'"text":"hi"' in drained
