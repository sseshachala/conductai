"""#2170 PR 3 — GatewayProfileClient streaming-path tests.

SSE reassembly of text + tool-call deltas, correlation ids from header and
SSE events, and terminal-state discipline (#2183).

Split from ``test_gateway_profile_client.py``. Environment bootstrap
(DATABASE_URL etc) is handled by tests/conftest.py.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from app.runtime.llm_client import GatewayProfileClient, LLMTextBlock, LLMToolUseBlock


# ─── PR 3 — streaming path ─────────────────────────────────────────────


class _FakeStreamResp:
    """Context-manager stand-in for httpx.stream(...)."""

    def __init__(self, lines: list[str], headers: dict | None = None, status: int = 200):
        self._lines = lines
        self.headers = headers or {}
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False

    def iter_lines(self):
        for ln in self._lines:
            yield ln

    def iter_bytes(self):
        # Only called on error paths; assemble the payload bytewise.
        yield ("\n".join(self._lines)).encode()


def _sse(*frames: dict) -> list[str]:
    """Format each dict as a ``data:`` SSE frame, terminated by [DONE]."""
    out: list[str] = []
    for f in frames:
        out.append("data: " + json.dumps(f))
        out.append("")  # blank separator between events
    out.append("data: [DONE]")
    return out


@patch("app.runtime.adapters.gateway_profile._httpx_stream_hook", None, create=True)
def _install_stream(monkeypatched):
    """Helper for readable @patch below — no-op used only to document intent."""
    return monkeypatched


def _patch_httpx_stream(fake: _FakeStreamResp):
    """Return a mock replacement for ``httpx.stream``."""
    def _fake_stream(_method, _url, **_kw):
        return fake
    return _fake_stream


def test_stream_reassembles_text_only():
    fake = _FakeStreamResp(_sse(
        {"id": "chatcmpl-1", "model": "gpt-4o-2024-05-13",
         "choices": [{"delta": {"content": "hel"}, "finish_reason": None}]},
        {"id": "chatcmpl-1",
         "choices": [{"delta": {"content": "lo"}, "finish_reason": None}]},
        {"id": "chatcmpl-1",
         "choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"id": "chatcmpl-1", "choices": [],
         "usage": {"prompt_tokens": 4, "completion_tokens": 2}},
    ))
    with patch("app.runtime.adapters.gateway_profile._httpx", create=True), \
         patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        resp = client.create(
            model="ignored",
            messages=[{"role": "user", "content": "hi"}],
            system="",
        )
    assert resp.stop_reason == "end_turn"
    assert isinstance(resp.content[0], LLMTextBlock)
    assert resp.content[0].text == "hello"
    assert resp.usage.input_tokens == 4
    assert resp.usage.output_tokens == 2


def test_stream_reassembles_tool_call_arguments_across_deltas():
    """OpenAI streams tool_calls with id/name on first delta and JSON
    arguments as fragments — must reassemble by index."""
    fake = _FakeStreamResp(_sse(
        {"id": "chatcmpl-2", "model": "gpt-4o",
         "choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_abc", "type": "function",
            "function": {"name": "read_file", "arguments": ""},
         }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '{"pa'},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": 'th":"/a"}'},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {"choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 3}},
    ))
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        resp = client.create(
            model="ignored",
            messages=[{"role": "user", "content": "read a"}],
            system="",
        )
    assert resp.stop_reason == "tool_use"
    tool_blocks = [b for b in resp.content if isinstance(b, LLMToolUseBlock)]
    assert len(tool_blocks) == 1
    tb = tool_blocks[0]
    assert tb.id == "call_abc"
    assert tb.name == "read_file"
    assert tb.input == {"path": "/a"}


def test_stream_reads_correlation_header_before_body():
    """Correlation header must be captured off the streaming response
    headers, not the reassembled body."""
    from app.modules.guard.tools_validator import encode_correlation_header
    corr = {"call_abc": "tcc_streamtest"}
    header_val = encode_correlation_header(corr)
    fake = _FakeStreamResp(
        _sse(
            {"choices": [{"delta": {"tool_calls": [{
                "index": 0, "id": "call_abc", "type": "function",
                "function": {"name": "read_file", "arguments": "{}"},
            }]}, "finish_reason": None}]},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        ),
        headers={"X-Conduct-Tool-Correlation-Ids": header_val},
    )
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        resp = client.create(
            model="ignored",
            messages=[{"role": "user", "content": "x"}],
            system="",
        )
    assert resp.correlation_ids == corr


def test_stream_does_not_send_stream_options_client_side():
    """Reviewer P1 (#2183): the canonical shim rejects ``stream_options``
    from the client (``extra_forbidden``). The shim itself injects
    ``stream_options.include_usage: true`` server-side when stream=true,
    so the outbound payload MUST NOT set it.
    """
    fake = _FakeStreamResp(_sse(
        {"choices": [{"delta": {"content": "x"}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
        {"choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1}},
    ))
    seen_body: dict = {}

    def _capture(_method, _url, **kw):
        seen_body.update(kw.get("json") or {})
        return fake

    with patch("httpx.stream", _capture):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        client.create(
            model="ignored",
            messages=[{"role": "user", "content": "x"}],
            system="",
        )
    assert seen_body.get("stream") is True
    assert "stream_options" not in seen_body, (
        f"stream_options must be injected server-side; found in outbound "
        f"payload: {seen_body.get('stream_options')!r}"
    )


def test_stream_error_raises_with_status():
    fake = _FakeStreamResp(
        ['{"error": {"message": "no such profile"}}'],
        status=404,
    )
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-UNKNOWN0",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        try:
            client.create(
                model="ignored",
                messages=[{"role": "user", "content": "x"}],
                system="",
            )
        except Exception as exc:
            assert "404" in str(exc)
            return
    raise AssertionError("expected exception on 4xx stream error")


# ─── Reviewer P1 (#2183): terminal-state discipline ────────────────────


def test_stream_error_sse_event_raises_terminal():
    """Reviewer P1: a top-level ``{"error": {...}}`` SSE frame must
    raise GatewayStreamError, not be treated as a completed turn.

    Reproduced from the review probe: post-inference tool-args validation
    refusal from the gateway is delivered as an error event followed by
    [DONE]. Prior code returned end_turn with empty content and marked
    the paid attempt as successful.
    """
    from app.runtime.adapters.gateway_profile import GatewayStreamError

    fake = _FakeStreamResp(_sse(
        {"choices": [{"delta": {"content": ""}, "finish_reason": None}]},
        {"error": {
            "message": "tool_call arguments failed validation",
            "type": "conduct_gateway_tool_arguments_validation_failed",
        }},
    ))
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        try:
            client.create(
                model="ignored",
                messages=[{"role": "user", "content": "x"}],
                system="",
            )
        except GatewayStreamError as exc:
            assert "conduct_gateway_tool_arguments_validation_failed" in str(exc)
            return
    raise AssertionError("expected GatewayStreamError on SSE error event")


def test_stream_incomplete_no_done_no_finish_raises():
    """Reviewer P1: EOF without [DONE] and no finish_reason → raise.

    Prior code defaulted finish_reason to 'stop' and returned end_turn
    on partial content, silently masking a truncated stream.
    """
    from app.runtime.adapters.gateway_profile import GatewayStreamError

    # No [DONE] terminator, no finish_reason on any choice.
    fake = _FakeStreamResp([
        "data: " + json.dumps(
            {"choices": [{"delta": {"content": "partial "}, "finish_reason": None}]}
        ),
        "",
        "data: " + json.dumps(
            {"choices": [{"delta": {"content": "text"}, "finish_reason": None}]}
        ),
    ])
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        try:
            client.create(
                model="ignored",
                messages=[{"role": "user", "content": "x"}],
                system="",
            )
        except GatewayStreamError as exc:
            assert "partial content" in str(exc) or "incomplete" in str(exc).lower() or "unsafe" in str(exc).lower()
            return
    raise AssertionError("expected GatewayStreamError on incomplete stream")


def test_stream_invalid_tool_call_arguments_raises_before_dispatch():
    """Reviewer P1: tool_call.arguments that isn't valid JSON at end of
    stream must raise, not reach the tool executor.
    """
    from app.runtime.adapters.gateway_profile import GatewayStreamError

    # id + name arrive; arguments fragments accumulate to malformed JSON.
    fake = _FakeStreamResp(_sse(
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_x", "type": "function",
            "function": {"name": "read_file", "arguments": ""},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "function": {"arguments": '{"path": '},
        }]}, "finish_reason": None}]},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ))
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        try:
            client.create(
                model="ignored",
                messages=[{"role": "user", "content": "x"}],
                system="",
            )
        except GatewayStreamError as exc:
            assert "non-JSON arguments" in str(exc)
            return
    raise AssertionError("expected GatewayStreamError on invalid tool_call args")


def test_stream_correlation_ids_via_sse_event():
    """Reviewer P2: correlation ids arrive inside SSE ``conduct``
    frames on streaming responses (headers get stripped by some hops).
    Must be captured onto ``LLMResponse.correlation_ids``.
    """
    fake = _FakeStreamResp(_sse(
        {"choices": [{"delta": {"tool_calls": [{
            "index": 0, "id": "call_1", "type": "function",
            "function": {"name": "read_file", "arguments": "{}"},
        }]}, "finish_reason": None}]},
        # Gateway emits correlation ids as a conduct meta-frame.
        {"conduct": {"tool_call_correlation_ids": {"call_1": "tcc_sse_test"}}},
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ))
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        resp = client.create(
            model="ignored",
            messages=[{"role": "user", "content": "x"}],
            system="",
        )
    assert resp.correlation_ids == {"call_1": "tcc_sse_test"}


def test_stream_correlation_ids_merges_sse_and_header():
    """Header + SSE both carry correlation ids for different calls; the
    adapter unions them so the runtime never loses a join key."""
    from app.modules.guard.tools_validator import encode_correlation_header

    header_val = encode_correlation_header({"call_hdr": "tcc_from_header"})
    fake = _FakeStreamResp(
        _sse(
            {"choices": [{"delta": {"tool_calls": [
                {"index": 0, "id": "call_hdr", "type": "function",
                 "function": {"name": "a", "arguments": "{}"}},
                {"index": 1, "id": "call_sse", "type": "function",
                 "function": {"name": "b", "arguments": "{}"}},
            ]}, "finish_reason": None}]},
            {"conduct": {"tool_call_correlation_ids": {"call_sse": "tcc_from_sse"}}},
            {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        ),
        headers={"X-Conduct-Tool-Correlation-Ids": header_val},
    )
    with patch("httpx.stream", _patch_httpx_stream(fake)):
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
            stream_enabled=True,
        )
        resp = client.create(
            model="ignored",
            messages=[{"role": "user", "content": "x"}],
            system="",
        )
    assert resp.correlation_ids == {
        "call_hdr": "tcc_from_header",
        "call_sse": "tcc_from_sse",
    }
