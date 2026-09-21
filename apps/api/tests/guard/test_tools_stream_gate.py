"""Unit tests for #2155 — streaming + tools with buffered-delta validation.

Pure-module tests. The wrapper takes an async byte iterator representing
an upstream SSE stream and yields validated bytes. No HTTP layer.

Each test frames a hand-built stream of OpenAI-shape SSE deltas, runs it
through ``wrap_tool_stream``, and asserts on the collected bytes: what
passed through, what was buffered, what was synthesized.
"""
from __future__ import annotations

import json
from typing import AsyncIterator

import pytest

from app.modules.guard.tools_stream_gate import (
    is_done_frame,
    wrap_tool_stream,
)


# ─── helpers ────────────────────────────────────────────────────────


def _sse(payload: dict) -> bytes:
    """Build one SSE ``data: <json>\\n\\n`` frame."""
    return b"data: " + json.dumps(payload).encode("utf-8") + b"\n\n"


def _done() -> bytes:
    return b"data: [DONE]\n\n"


async def _iter(chunks: list[bytes]) -> AsyncIterator[bytes]:
    for c in chunks:
        yield c


async def _drain(chunks: list[bytes]) -> list[dict | str]:
    """Run wrap_tool_stream and return decoded frames.

    Frames that parse as JSON come back as dicts; the ``[DONE]`` sentinel
    comes back as the string ``"[DONE]"``. Non-parseable frames come back
    as raw strings so tests can assert on them directly.
    """
    out: list[dict | str] = []
    combined = bytearray()
    async for chunk in wrap_tool_stream(_iter(chunks)):
        combined.extend(chunk)
    # Frames arrive already \n\n-separated in the wrapper output. Split
    # on the same boundary so a stream with N frames comes back as N
    # entries (empty tail after trailing separator dropped).
    for raw in bytes(combined).split(b"\n\n"):
        raw = raw.strip()
        if not raw:
            continue
        if raw.startswith(b"data: "):
            body = raw[len(b"data: "):]
            if body == b"[DONE]":
                out.append("[DONE]")
                continue
            try:
                out.append(json.loads(body.decode("utf-8")))
            except json.JSONDecodeError:
                out.append(raw.decode("utf-8"))
        else:
            out.append(raw.decode("utf-8"))
    return out


# ─── is_done_frame ─────────────────────────────────────────────────


class TestIsDoneFrame:
    def test_done_frame(self) -> None:
        assert is_done_frame(b"data: [DONE]") is True

    def test_json_frame_not_done(self) -> None:
        assert is_done_frame(b'data: {"x": 1}') is False

    def test_comment_not_done(self) -> None:
        assert is_done_frame(b": keepalive") is False


# ─── text passthrough (no tools) ───────────────────────────────────


@pytest.mark.anyio('asyncio')
class TestTextPassthrough:
    async def test_text_only_stream_unchanged(self) -> None:
        # Baseline: no tool_calls anywhere. Every text delta reaches
        # the client in order + a final [DONE].
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"content": "hello "}, "finish_reason": None}]}),
            _sse({"choices": [{"index": 0, "delta": {"content": "world"}, "finish_reason": None}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
            _done(),
        ]
        out = await _drain(chunks)
        # 3 text/finish frames + [DONE]. Order preserved.
        assert len(out) == 4
        assert out[0]["choices"][0]["delta"]["content"] == "hello "
        assert out[1]["choices"][0]["delta"]["content"] == "world"
        assert out[2]["choices"][0]["finish_reason"] == "stop"
        assert out[-1] == "[DONE]"


# ─── tool_call buffered + emitted synthetic ────────────────────────


@pytest.mark.anyio('asyncio')
class TestToolCallBuffering:
    async def test_single_tool_call_arg_fragments_buffered_then_flushed(self) -> None:
        # Model emits ``{"city": "SF"}`` split across 4 arg fragments.
        # Wrapper holds all 4 back and emits one synthetic tool_calls
        # frame with the assembled + redacted args.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "id": "call_abc", "type": "function",
                                "function": {"name": "get_weather", "arguments": ""}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "function": {"arguments": '{"'}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "function": {"arguments": 'city'}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "function": {"arguments": '": "SF"}'}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
            _done(),
        ]
        out = await _drain(chunks)

        # Only 3 frames leave the wrapper: synthesized tool_calls,
        # finish frame, [DONE]. None of the 4 fragment frames pass
        # through — the invariant is "no partial arg bytes reach the
        # client."
        assert len(out) == 3
        synth = out[0]
        assert synth["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "get_weather"
        assert synth["choices"][0]["delta"]["tool_calls"][0]["function"]["arguments"] == '{"city": "SF"}'
        assert synth["choices"][0]["delta"]["tool_calls"][0]["id"] == "call_abc"
        assert out[1]["choices"][0]["finish_reason"] == "tool_calls"
        assert out[-1] == "[DONE]"

    async def test_text_before_tool_call_passes_through(self) -> None:
        # Assistant emits some text, then decides to call a tool.
        # Text streams live; tool_calls buffer.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"content": "Checking..."}}]}),
            _sse({"choices": [{"index": 0, "delta": {
                "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                "function": {"name": "search", "arguments": "{}"}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
            _done(),
        ]
        out = await _drain(chunks)
        # Text frame first (passthrough), synthesized tool_calls, finish, [DONE]
        assert out[0]["choices"][0]["delta"]["content"] == "Checking..."
        assert out[1]["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "search"
        assert out[2]["choices"][0]["finish_reason"] == "tool_calls"
        assert out[-1] == "[DONE]"

    async def test_multiple_parallel_tool_calls_flushed_together(self) -> None:
        # Model calls TWO tools in parallel; both flush in one synthetic
        # frame after finish_reason.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_a", "type": "function",
                 "function": {"name": "tool_a", "arguments": ""}},
                {"index": 1, "id": "call_b", "type": "function",
                 "function": {"name": "tool_b", "arguments": ""}},
            ]}}]}),
            _sse({"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "function": {"arguments": '{"a":1}'}},
                {"index": 1, "function": {"arguments": '{"b":2}'}},
            ]}}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
            _done(),
        ]
        out = await _drain(chunks)
        assert len(out) == 3
        tcs = out[0]["choices"][0]["delta"]["tool_calls"]
        assert len(tcs) == 2
        # Compare parsed args, not the raw JSON string — the redactor
        # re-serializes with default separators (spaces), which is a
        # cosmetic difference the client's SDK doesn't care about.
        by_name = {t["function"]["name"]: json.loads(t["function"]["arguments"]) for t in tcs}
        assert by_name == {"tool_a": {"a": 1}, "tool_b": {"b": 2}}


# ─── validation failure paths ──────────────────────────────────────


@pytest.mark.anyio('asyncio')
class TestValidationFailure:
    async def test_invalid_json_arguments_emit_error_frame(self) -> None:
        # Model streams garbage JSON. Wrapper refuses the tool_call and
        # emits an error frame INSTEAD of a synthesized tool_calls
        # frame. The finish frame still gets through so the SDK closes
        # the stream cleanly.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_1", "type": "function",
                 "function": {"name": "x", "arguments": "not-json {{{"}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]}),
            _done(),
        ]
        out = await _drain(chunks)
        # First frame is the synthesized error, not a tool_calls frame.
        assert "error" in out[0]
        assert out[0]["error"]["type"] == "conduct_gateway_tool_arguments_validation_failed"
        assert out[0]["error"]["gate"] == "response-stream"
        # No tool_calls survived to the client.
        for frame in out:
            if isinstance(frame, dict) and "choices" in frame:
                for choice in frame["choices"]:
                    assert not (choice.get("delta") or {}).get("tool_calls")
        assert out[-1] == "[DONE]"

    async def test_premature_finish_reason_stop_emits_error(self) -> None:
        # Tool_call buffer open, but upstream sends finish_reason="stop"
        # (not "tool_calls"). That's a contract violation from the
        # provider — we refuse to guess what the caller wanted.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_x", "type": "function",
                 "function": {"name": "x", "arguments": '{"partial":'}}]}}]}),
            _sse({"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}),
            _done(),
        ]
        out = await _drain(chunks)
        assert "error" in out[0]
        assert "stop" in out[0]["error"]["detail"]
        assert out[-1] == "[DONE]"

    async def test_stream_ends_before_finish_reason(self) -> None:
        # Upstream disconnects mid-stream: tool_call was buffered but no
        # finish_reason arrived. Wrapper emits an error frame at
        # end-of-stream so the client doesn't hang.
        chunks = [
            _sse({"choices": [{"index": 0, "delta": {"tool_calls": [
                {"index": 0, "id": "call_y", "type": "function",
                 "function": {"name": "y", "arguments": '{"a":'}}]}}]}),
            # No finish frame, no [DONE] — stream just ends.
        ]
        out = await _drain(chunks)
        assert any(isinstance(f, dict) and "error" in f for f in out)
        assert out[-1] == "[DONE]"  # synthesized terminal marker


# ─── frame splitting ───────────────────────────────────────────────


@pytest.mark.anyio('asyncio')
class TestFrameSplitting:
    async def test_chunk_split_across_boundary(self) -> None:
        # Upstream socket delivers bytes without respecting SSE frame
        # boundaries. Wrapper must reassemble.
        payload_a = _sse({"choices": [{"index": 0, "delta": {"content": "ab"}}]})
        payload_b = _sse({"choices": [{"index": 0, "delta": {"content": "cd"}}]})
        merged = payload_a + payload_b + _done()
        # Slice the concatenated stream into two chunks that split MID-
        # frame — first chunk cuts off inside payload_b.
        cut = len(payload_a) + 5
        chunks = [merged[:cut], merged[cut:]]
        out = await _drain(chunks)
        assert out[0]["choices"][0]["delta"]["content"] == "ab"
        assert out[1]["choices"][0]["delta"]["content"] == "cd"
        assert out[-1] == "[DONE]"

    async def test_keepalive_comment_passes_through(self) -> None:
        # SSE comment lines start with ':'. Providers use them as
        # keepalives on long generations. They must not confuse the
        # buffer.
        chunks = [
            b": keepalive\n\n",
            _sse({"choices": [{"index": 0, "delta": {"content": "hi"}}]}),
            _done(),
        ]
        out = await _drain(chunks)
        # Comment reaches output (as a raw string, not a dict).
        assert any(isinstance(f, str) and f.startswith(":") for f in out)
        assert any(isinstance(f, dict) and f.get("choices", [{}])[0].get("delta", {}).get("content") == "hi" for f in out)
        assert out[-1] == "[DONE]"
