"""#2170 PR 2 — GatewayProfileClient adapter tests.

Verify the canonical envelope the client sends, that OpenAI chat-shape
responses convert into LLMResponse blocks, and that the
``X-Conduct-Tool-Correlation-Ids`` header lands on
``LLMResponse.correlation_ids`` so brain_block can emit the join key
into run_events.

Environment bootstrap (DATABASE_URL etc) is handled by tests/conftest.py.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.runtime.llm_client import GatewayProfileClient, LLMTextBlock, LLMToolUseBlock


def _mock_response(json_body: dict, headers: dict | None = None, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.text = json.dumps(json_body)
    resp.json.return_value = json_body
    resp.headers = headers or {}
    return resp


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_sends_canonical_envelope(mock_post):
    """Body carries ``profile``, not ``model``; URL is /completions."""
    mock_post.return_value = _mock_response({
        "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    })

    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345-default",
        base_url="https://gw.example.com/gateway/v1",
        default_headers={"x-conductai-internal": "cond_run_test"},
    )
    resp = client.create(
        model="ignored",
        messages=[{"role": "user", "content": "hi"}],
        system="be concise",
        max_tokens=64,
    )

    kwargs = mock_post.call_args.kwargs
    assert kwargs["url"] == "https://gw.example.com/gateway/v1/completions"
    payload = kwargs["json_body"]
    assert payload["profile"] == "cond-ABC12345-default"
    assert "model" not in payload
    assert payload["max_tokens"] == 64
    assert payload["stream"] is False
    # System prompt is prepended as a system message (OpenAI-shape).
    assert payload["messages"][0] == {"role": "system", "content": "be concise"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    # Auth headers passed through verbatim; gateway auths on x-conductai-internal.
    assert kwargs["headers"]["x-conductai-internal"] == "cond_run_test"

    assert resp.stop_reason == "end_turn"
    assert resp.usage.input_tokens == 5
    assert resp.usage.output_tokens == 3
    assert isinstance(resp.content[0], LLMTextBlock) and resp.content[0].text == "hello"


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_converts_tools_to_openai_function_shape(mock_post):
    """BRAIN_TOOLS ``input_schema`` becomes ``function.parameters``."""
    mock_post.return_value = _mock_response({
        "choices": [{"message": {"content": ""}, "finish_reason": "stop"}],
        "usage": {},
    })

    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
        tools=[{
            "name": "read_file",
            "description": "read a file",
            "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}},
        }],
    )

    payload = mock_post.call_args.kwargs["json_body"]
    assert payload["tools"] == [{
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "read a file",
            "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
        },
    }]


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_maps_tool_calls_to_tool_use_blocks(mock_post):
    """OpenAI tool_calls → LLMToolUseBlock; finish_reason=tool_calls → tool_use."""
    mock_post.return_value = _mock_response({
        "choices": [{
            "message": {
                "content": "",
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "read_file", "arguments": '{"path":"/a"}'},
                }],
            },
            "finish_reason": "tool_calls",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 4},
    })

    client = GatewayProfileClient(
        profile_cond_code="cond-XYZ98765",
        base_url="https://gw.example.com/gateway/v1",
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


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_reads_correlation_header(mock_post):
    """X-Conduct-Tool-Correlation-Ids parses onto LLMResponse.correlation_ids."""
    from app.modules.guard.tools_validator import encode_correlation_header
    corr = {"call_1": "tcc_deadbeef"}
    header_val = encode_correlation_header(corr)
    mock_post.return_value = _mock_response(
        json_body={
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{}"},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {},
        },
        headers={"X-Conduct-Tool-Correlation-Ids": header_val},
    )

    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    resp = client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
    )
    assert resp.correlation_ids == corr


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_missing_correlation_header_is_empty(mock_post):
    """No header → correlation_ids is an empty dict, not an error."""
    mock_post.return_value = _mock_response({
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    })

    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    resp = client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
    )
    assert resp.correlation_ids == {}


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_raises_on_4xx(mock_post):
    """4xx from the gateway surfaces as a plain exception (dag_runner handles)."""
    mock_post.return_value = _mock_response({"error": {"message": "no such profile"}}, status=404)
    client = GatewayProfileClient(
        profile_cond_code="cond-UNKNOWN0",
        base_url="https://gw.example.com/gateway/v1",
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
    raise AssertionError("expected exception on 4xx")


def test_make_assistant_turn_mirrors_openai_shape():
    from app.runtime.llm_client import LLMResponse, LLMUsage
    resp = LLMResponse(
        content=[],
        stop_reason="tool_use",
        usage=LLMUsage(),
        _raw_content={"content": "ok", "tool_calls": [{"id": "call_1"}]},
    )
    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    turn = client.make_assistant_turn(resp)
    assert turn == [{"role": "assistant", "content": "ok", "tool_calls": [{"id": "call_1"}]}]


def test_make_tool_results_turn_mirrors_openai_shape():
    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    turn = client.make_tool_results_turn([("call_1", "42"), ("call_2", "hello")])
    assert turn == [
        {"role": "tool", "tool_call_id": "call_1", "content": "42"},
        {"role": "tool", "tool_call_id": "call_2", "content": "hello"},
    ]


# ─── Reviewer P1 fixes (#2182) ─────────────────────────────────────────


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_forces_single_attempt(mock_post):
    """Reviewer P1: adapter must not retry — gateway owns retry policy.

    A terminal ``conduct_gateway_tool_arguments_validation_failed`` 502
    is an already-paid attempt; retrying triples inference cost. Verify
    the adapter passes ``max_attempts=1`` regardless of ``outer_attempt``.
    """
    mock_post.return_value = _mock_response({
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    })
    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
    )
    client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
        outer_attempt=1,
    )
    assert mock_post.call_args.kwargs["max_attempts"] == 1

    mock_post.reset_mock()
    mock_post.return_value = _mock_response({
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {},
    })
    client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
        outer_attempt=3,
    )
    assert mock_post.call_args.kwargs["max_attempts"] == 1


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_computes_cost_for_known_provider_prefix(mock_post):
    """Reviewer P1: response ``model`` + ``usage`` produces non-zero cost.

    brain_block's per-block ``max_cost_usd`` cap sums ``cost_usd`` across
    turns. Returning 0.0 (as the initial PR did) silently disables the
    cap. Verify a Claude model with real token usage produces positive
    cost through the pricing snapshot.
    """
    from app.runtime.pricing import freeze_pricing_snapshot
    snap = freeze_pricing_snapshot()

    mock_post.return_value = _mock_response({
        "model": "claude-3-5-sonnet-20240620",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000},
    })
    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
        pricing_snapshot=snap,
    )
    resp = client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
    )
    assert resp.cost_usd > 0.0, (
        f"expected positive cost from 1M+500K tokens on claude-3-5-sonnet, "
        f"got {resp.cost_usd}"
    )


@patch("app.runtime.adapters.gateway_profile.post_with_retry")
def test_create_zero_cost_for_unknown_model_prefix(mock_post):
    """Unknown model prefix → 0 cost, no crash.

    Prefix heuristic can't cover every future model. Recording 0 is
    safer than misattributing; the gateway audit row has authoritative
    cost regardless.
    """
    from app.runtime.pricing import freeze_pricing_snapshot
    snap = freeze_pricing_snapshot()

    mock_post.return_value = _mock_response({
        "model": "some-future-model-nobody-knows",
        "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50},
    })
    client = GatewayProfileClient(
        profile_cond_code="cond-ABC12345",
        base_url="https://gw.example.com/gateway/v1",
        pricing_snapshot=snap,
    )
    resp = client.create(
        model="ignored",
        messages=[{"role": "user", "content": "x"}],
        system="",
    )
    assert resp.cost_usd == 0.0


def test_infer_provider_from_model_covers_shipped_prefixes():
    from app.runtime.adapters.gateway_profile import _infer_provider_from_model
    assert _infer_provider_from_model("claude-3-5-sonnet-20240620") == "anthropic"
    assert _infer_provider_from_model("gpt-4o-2024-05-13") == "openai"
    assert _infer_provider_from_model("o1-preview") == "openai"
    assert _infer_provider_from_model("sonar-pro") == "perplexity"
    assert _infer_provider_from_model("meta-llama/llama-3.1-70b") == "together"
    assert _infer_provider_from_model("") is None
    assert _infer_provider_from_model("no-such-prefix-xyz") is None


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


def test_stream_sends_include_usage_option():
    """stream_enabled=True must inject stream_options.include_usage=true.
    Without it the SSE contract drops the final usage frame and cost cap fails.
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
    assert seen_body.get("stream_options") == {"include_usage": True}


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


def test_stream_off_by_default_uses_non_streaming_path():
    """stream_enabled=False (default) keeps the existing non-streaming path."""
    with patch("app.runtime.adapters.gateway_profile.post_with_retry") as mock_post:
        mock_post.return_value = _mock_response({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {},
        })
        client = GatewayProfileClient(
            profile_cond_code="cond-ABC12345",
            base_url="https://gw.example.com/gateway/v1",
        )
        client.create(
            model="ignored",
            messages=[{"role": "user", "content": "x"}],
            system="",
        )
        assert mock_post.call_args.kwargs["json_body"]["stream"] is False
        assert "stream_options" not in mock_post.call_args.kwargs["json_body"]
