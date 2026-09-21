"""Round-trip tests for the canonical ↔ Anthropic converter (#2157).

The converter is bidirectional: canonical OpenAI-shape body →
Anthropic Messages body on the request side; Anthropic Messages
response → canonical OpenAI Chat Completions on the response side.

Tests are structured around the three areas most likely to drift:

  1. Message shape rewriting (system extraction, role: "tool" →
     tool_result blocks, assistant tool_calls → tool_use blocks).
  2. Tools + tool_choice shape (parameters → input_schema, three-mode
     rewrite, named-choice → tool-name form).
  3. Response normalization (content array → message/tool_calls,
     stop_reason mapping, usage field rename).
"""
from __future__ import annotations

import json

import pytest

from app.modules.guard.tools_anthropic_converter import (
    ConverterError,
    anthropic_to_canonical,
    canonical_to_anthropic,
)


# ─── Request side: canonical → Anthropic ────────────────────────────


class TestBasicPassthrough:
    def test_simple_user_message(self) -> None:
        body = {
            "model": "claude-3-5-sonnet",
            "messages": [{"role": "user", "content": "hello"}],
            "max_tokens": 128,
        }
        out = canonical_to_anthropic(body)
        assert out["model"] == "claude-3-5-sonnet"
        assert out["max_tokens"] == 128
        assert out["messages"] == [{"role": "user", "content": "hello"}]
        assert "system" not in out

    def test_temperature_top_p_stream_forwarded(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [{"role": "user", "content": "x"}],
            "temperature": 0.5, "top_p": 0.9, "stream": True,
        }
        out = canonical_to_anthropic(body)
        assert out["temperature"] == 0.5
        assert out["top_p"] == 0.9
        assert out["stream"] is True

    def test_stop_string_becomes_stop_sequences_list(self) -> None:
        body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}], "stop": "\n\n"}
        out = canonical_to_anthropic(body)
        assert out["stop_sequences"] == ["\n\n"]

    def test_stop_list_forwarded_verbatim(self) -> None:
        body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}], "stop": ["\n", "END"]}
        out = canonical_to_anthropic(body)
        assert out["stop_sequences"] == ["\n", "END"]

    def test_non_dict_body_raises(self) -> None:
        with pytest.raises(ConverterError) as e:
            canonical_to_anthropic("not a dict")  # type: ignore[arg-type]
        assert e.value.direction == "canonical_to_anthropic"


class TestSystemExtraction:
    def test_single_system_message_extracted(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "hi"},
            ],
        }
        out = canonical_to_anthropic(body)
        assert out["system"] == "You are helpful."
        assert out["messages"] == [{"role": "user", "content": "hi"}]

    def test_multiple_system_messages_concatenated(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "system", "content": "line one"},
                {"role": "system", "content": "line two"},
                {"role": "user", "content": "x"},
            ],
        }
        out = canonical_to_anthropic(body)
        assert out["system"] == "line one\nline two"


class TestAssistantToolCallsConversion:
    def test_assistant_text_only(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "hello"},
            ],
        }
        out = canonical_to_anthropic(body)
        assert out["messages"][-1] == {"role": "assistant", "content": "hello"}

    def test_assistant_null_content_with_tool_calls(self) -> None:
        # Canonical form: content=None, tool_calls=[...].
        # Anthropic form: content=[{type: "tool_use", ...}].
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "weather?"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": json.dumps({"city": "SF"}),
                        },
                    }],
                },
            ],
        }
        out = canonical_to_anthropic(body)
        assert out["messages"][-1] == {
            "role": "assistant",
            "content": [{
                "type": "tool_use",
                "id": "call_1",
                "name": "get_weather",
                "input": {"city": "SF"},
            }],
        }

    def test_assistant_text_and_tool_call(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "x"},
                {
                    "role": "assistant", "content": "Let me check.",
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }],
                },
            ],
        }
        out = canonical_to_anthropic(body)
        assistant = out["messages"][-1]
        assert assistant["role"] == "assistant"
        # Both text and tool_use blocks — text first (matches upstream
        # semantics: model preface, then the actual call).
        assert assistant["content"][0] == {"type": "text", "text": "Let me check."}
        assert assistant["content"][1]["type"] == "tool_use"

    def test_broken_arguments_json_becomes_empty_input(self) -> None:
        # tools_validator should have blocked this pre-dispatch, but if
        # a broken payload reaches the converter we don't want to
        # forward invalid JSON — treat as empty input.
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "x"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "x", "arguments": "{not-json"},
                    }],
                },
            ],
        }
        out = canonical_to_anthropic(body)
        tool_use = out["messages"][-1]["content"][0]
        assert tool_use["type"] == "tool_use"
        assert tool_use["input"] == {}


class TestToolResultConversion:
    def test_role_tool_becomes_user_tool_result_block(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "assistant", "content": "checking"},
                {"role": "tool", "content": "72F, sunny", "tool_call_id": "call_1"},
            ],
        }
        out = canonical_to_anthropic(body)
        tool_result_turn = out["messages"][-1]
        assert tool_result_turn["role"] == "user"
        assert tool_result_turn["content"] == [{
            "type": "tool_result",
            "tool_use_id": "call_1",
            "content": "72F, sunny",
        }]

    def test_tool_role_without_call_id_dropped(self) -> None:
        # Defensive: validator rejects earlier. If we reach here,
        # skip rather than emit a malformed Anthropic block.
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "tool", "content": "orphan"},  # no tool_call_id
            ],
        }
        out = canonical_to_anthropic(body)
        # Only the user message survives.
        assert out["messages"] == [{"role": "user", "content": "x"}]


# ─── Tools + tool_choice rewrite ────────────────────────────────────


class TestToolsRewrite:
    def test_openai_tool_becomes_anthropic_shape(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [{"role": "user", "content": "x"}],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Look up the weather.",
                    "parameters": {
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                },
            }],
        }
        out = canonical_to_anthropic(body)
        assert out["tools"] == [{
            "name": "get_weather",
            "description": "Look up the weather.",
            "input_schema": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        }]

    def test_missing_description_omitted(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [{"role": "user", "content": "x"}],
            "tools": [{"type": "function", "function": {"name": "n"}}],
        }
        out = canonical_to_anthropic(body)
        assert out["tools"] == [{"name": "n"}]


class TestToolChoiceRewrite:
    def test_auto_becomes_type_auto(self) -> None:
        body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}], "tool_choice": "auto"}
        out = canonical_to_anthropic(body)
        assert out["tool_choice"] == {"type": "auto"}

    def test_required_becomes_type_any(self) -> None:
        body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}], "tool_choice": "required"}
        out = canonical_to_anthropic(body)
        assert out["tool_choice"] == {"type": "any"}

    def test_none_maps_to_type_none(self) -> None:
        # Reviewer P2 #5 (2026-09-20): Anthropic does support
        # {"type":"none"}; the previous "omit" behavior let Anthropic
        # default-auto-select tools the caller had disabled.
        body = {"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "x"}], "tool_choice": "none"}
        out = canonical_to_anthropic(body)
        assert out["tool_choice"] == {"type": "none"}

    def test_named_function_becomes_type_tool(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [{"role": "user", "content": "x"}],
            "tool_choice": {"type": "function", "function": {"name": "get_weather"}},
        }
        out = canonical_to_anthropic(body)
        assert out["tool_choice"] == {"type": "tool", "name": "get_weather"}


# ─── Response side: Anthropic → canonical ───────────────────────────


class TestResponseSimpleText:
    def test_text_only_response(self) -> None:
        resp = {
            "id": "msg_abc", "model": "claude-3-5-sonnet",
            "role": "assistant", "type": "message",
            "content": [{"type": "text", "text": "hello world"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 5, "output_tokens": 2},
        }
        out = anthropic_to_canonical(resp)
        assert out["object"] == "chat.completion"
        assert out["id"] == "msg_abc"
        assert out["model"] == "claude-3-5-sonnet"
        assert out["choices"][0]["message"] == {
            "role": "assistant", "content": "hello world",
        }
        assert out["choices"][0]["finish_reason"] == "stop"
        assert out["usage"] == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7}

    def test_missing_content_becomes_empty_text(self) -> None:
        resp = {"id": "x", "content": [], "stop_reason": "end_turn"}
        out = anthropic_to_canonical(resp)
        assert out["choices"][0]["message"]["content"] == ""


class TestResponseToolUse:
    def test_single_tool_use_block(self) -> None:
        resp = {
            "id": "msg_1", "model": "m",
            "content": [{
                "type": "tool_use",
                "id": "toolu_abc",
                "name": "get_weather",
                "input": {"city": "SF"},
            }],
            "stop_reason": "tool_use",
        }
        out = anthropic_to_canonical(resp)
        message = out["choices"][0]["message"]
        assert message["role"] == "assistant"
        # Content null when tool_calls present per OpenAI contract.
        assert message["content"] is None
        assert message["tool_calls"] == [{
            "id": "toolu_abc",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"city": "SF"}),
            },
        }]
        assert out["choices"][0]["finish_reason"] == "tool_calls"

    def test_text_plus_tool_use(self) -> None:
        resp = {
            "id": "msg_1", "model": "m",
            "content": [
                {"type": "text", "text": "Let me check the weather."},
                {"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "SF"}},
            ],
            "stop_reason": "tool_use",
        }
        out = anthropic_to_canonical(resp)
        message = out["choices"][0]["message"]
        # Text preserved as content; tool_call in tool_calls.
        assert message["content"] == "Let me check the weather."
        assert len(message["tool_calls"]) == 1

    def test_stop_reason_max_tokens_maps_to_length(self) -> None:
        resp = {"content": [{"type": "text", "text": "x"}], "stop_reason": "max_tokens"}
        out = anthropic_to_canonical(resp)
        assert out["choices"][0]["finish_reason"] == "length"

    def test_multiple_tool_use_blocks(self) -> None:
        resp = {
            "content": [
                {"type": "tool_use", "id": "a", "name": "search", "input": {}},
                {"type": "tool_use", "id": "b", "name": "email", "input": {"to": "x"}},
            ],
            "stop_reason": "tool_use",
        }
        out = anthropic_to_canonical(resp)
        message = out["choices"][0]["message"]
        assert [tc["function"]["name"] for tc in message["tool_calls"]] == ["search", "email"]

    def test_non_dict_response_raises(self) -> None:
        with pytest.raises(ConverterError):
            anthropic_to_canonical("not a dict")  # type: ignore[arg-type]


# ─── Round-trip: canonical → Anthropic → canonical parity ──────────


class TestRoundTrip:
    """Real workflow: canonical body sent in, canonical response back.

    Not a byte-for-byte round trip (we don't reproduce upstream's model
    output), but proves the shape survives both directions in a way a
    downstream client would recognize.
    """

    def test_tool_call_lifecycle(self) -> None:
        # Turn 1: caller sends canonical tools request.
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Weather in SF?"},
            ],
            "tools": [{
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
                },
            }],
        }
        anth_req = canonical_to_anthropic(req)
        assert anth_req["system"] == "You are helpful."
        assert anth_req["tools"][0]["name"] == "get_weather"

        # Simulated upstream response.
        anth_resp = {
            "id": "msg_1", "model": "claude-3-5-sonnet",
            "content": [{"type": "tool_use", "id": "tu_1", "name": "get_weather", "input": {"city": "SF"}}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 12, "output_tokens": 4},
        }
        canon_resp = anthropic_to_canonical(anth_resp)
        message = canon_resp["choices"][0]["message"]
        assert message["tool_calls"][0]["function"]["name"] == "get_weather"
        # Arguments back in JSON-string form per OpenAI contract.
        assert json.loads(message["tool_calls"][0]["function"]["arguments"]) == {"city": "SF"}
        assert canon_resp["choices"][0]["finish_reason"] == "tool_calls"

        # Turn 2: caller supplies tool_result as canonical role: "tool".
        req2 = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Weather in SF?"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "tu_1", "type": "function",
                        "function": {"name": "get_weather", "arguments": json.dumps({"city": "SF"})},
                    }],
                },
                {"role": "tool", "content": "72F, sunny", "tool_call_id": "tu_1"},
            ],
        }
        anth_req2 = canonical_to_anthropic(req2)
        # Assistant turn preserved as tool_use block.
        assistant_turn = next(m for m in anth_req2["messages"] if m["role"] == "assistant")
        assert assistant_turn["content"][0]["type"] == "tool_use"
        # Tool result turn appears as user turn with tool_result block.
        user_turns = [m for m in anth_req2["messages"] if m["role"] == "user"]
        # First user turn is the original prompt; second carries the tool_result.
        assert user_turns[-1]["content"][0]["type"] == "tool_result"
        assert user_turns[-1]["content"][0]["tool_use_id"] == "tu_1"
        assert user_turns[-1]["content"][0]["content"] == "72F, sunny"


# ─── #2166 PR 2 — vision content conversion ────────────────────────


class TestVisionConversion:
    """Anthropic-target ``image_url`` → ``image`` block conversion."""

    def test_https_url_becomes_url_source(self) -> None:
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "what's this?"},
                    {"type": "image_url", "image_url": {
                        "url": "https://example.com/pic.png",
                    }},
                ],
            }],
        }
        out = canonical_to_anthropic(req)
        content = out["messages"][0]["content"]
        assert content[0] == {"type": "text", "text": "what's this?"}
        assert content[1]["type"] == "image"
        assert content[1]["source"] == {
            "type": "url", "url": "https://example.com/pic.png",
        }

    def test_data_url_becomes_base64_source(self) -> None:
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [{"type": "image_url", "image_url": {
                    "url": "data:image/jpeg;base64,QUFBQQ==",
                }}],
            }],
        }
        out = canonical_to_anthropic(req)
        block = out["messages"][0]["content"][0]
        assert block["type"] == "image"
        assert block["source"] == {
            "type": "base64",
            "media_type": "image/jpeg",
            "data": "QUFBQQ==",
        }

    def test_data_url_with_charset_media_type_stripped(self) -> None:
        # data:image/png;charset=utf-8;base64,... — only the media
        # type up to the first ``;`` counts; charset extras are dropped.
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [{"type": "image_url", "image_url": {
                    "url": "data:image/png;charset=utf-8;base64,QUFBQQ==",
                }}],
            }],
        }
        out = canonical_to_anthropic(req)
        block = out["messages"][0]["content"][0]
        assert block["source"]["media_type"] == "image/png"

    def test_mixed_text_and_multiple_images_preserved_in_order(self) -> None:
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": "compare"},
                    {"type": "image_url", "image_url": {"url": "https://a/1.png"}},
                    {"type": "image_url", "image_url": {"url": "https://b/2.png"}},
                    {"type": "text", "text": "and describe"},
                ],
            }],
        }
        out = canonical_to_anthropic(req)
        content = out["messages"][0]["content"]
        assert [p["type"] for p in content] == ["text", "image", "image", "text"]
        assert content[1]["source"]["url"] == "https://a/1.png"
        assert content[2]["source"]["url"] == "https://b/2.png"

    def test_string_content_still_passes_through(self) -> None:
        # Baseline — non-multimodal content still works unchanged.
        req = {
            "model": "cond-x-claude",
            "max_tokens": 128,
            "messages": [{"role": "user", "content": "plain text"}],
        }
        out = canonical_to_anthropic(req)
        assert out["messages"][0] == {"role": "user", "content": "plain text"}
