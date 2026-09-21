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
