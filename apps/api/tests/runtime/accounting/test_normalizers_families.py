"""Family normalizer self-checks — JSON + SSE parity per provider family.

Covers the acceptance-test bullets in #2209 §Phase 1: fresh vs cache reads
vs cache writes, cached-input semantics, reasoning subset, legitimate zero,
omitted usage, interrupted streams.
"""

from __future__ import annotations

import json

import pytest

from app.runtime.accounting import (
    ProviderFamily,
    UsageCompleteness,
    UsageOrigin,
    normalize_json,
    normalize_sse,
)


# ─── Anthropic Messages ────────────────────────────────────────────────────────


def test_anthropic_json_with_flat_cache_creation():
    body = {
        "usage": {
            "input_tokens": 100,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 50,
            "output_tokens": 40,
        }
    }
    result = normalize_json(ProviderFamily.ANTHROPIC_MESSAGES, body)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.uncached_input_tokens == 100
    assert result.tokens.cache_read_tokens == 50
    assert result.tokens.cache_write_tokens_by_tier == {"ephemeral_5m": 200}
    # Anthropic input_tokens does NOT include cache reads/writes — total is sum.
    assert result.tokens.total_input_tokens == 100 + 50 + 200
    assert result.tokens.total_output_tokens == 40


def test_anthropic_json_with_tiered_cache_creation():
    body = {
        "usage": {
            "input_tokens": 100,
            "cache_creation": {
                "ephemeral_5m_input_tokens": 150,
                "ephemeral_1h_input_tokens": 50,
            },
            "cache_read_input_tokens": 0,
            "output_tokens": 40,
        }
    }
    result = normalize_json(ProviderFamily.ANTHROPIC_MESSAGES, body)
    assert result.tokens.cache_write_tokens_by_tier == {
        "ephemeral_5m": 150,
        "ephemeral_1h": 50,
    }
    assert result.tokens.cache_read_tokens == 0  # legitimate zero, not None


def test_anthropic_json_missing_usage_is_unavailable():
    result = normalize_json(ProviderFamily.ANTHROPIC_MESSAGES, {"message": "hi"})
    assert result.completeness is UsageCompleteness.UNAVAILABLE
    assert result.origin is UsageOrigin.MISSING


def test_anthropic_sse_complete_stream():
    sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"cache_read_input_tokens":20,"output_tokens":1}}}\n\n'
        b"event: message_delta\n"
        b'data: {"type":"message_delta","usage":{"output_tokens":50}}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )
    result = normalize_sse(ProviderFamily.ANTHROPIC_MESSAGES, sse)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_output_tokens == 50
    assert result.tokens.cache_read_tokens == 20
    assert result.origin is UsageOrigin.NORMALIZED_STREAM


def test_anthropic_sse_interrupted_before_message_delta():
    """Client dropped after message_start — we have input tokens but no
    final output. Completeness = PARTIAL. Invariant #7: partial charge may
    still apply."""
    sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
    )
    result = normalize_sse(ProviderFamily.ANTHROPIC_MESSAGES, sse)
    assert result.completeness is UsageCompleteness.PARTIAL
    assert result.tokens.total_input_tokens is not None


def test_anthropic_sse_empty_stream():
    result = normalize_sse(ProviderFamily.ANTHROPIC_MESSAGES, b"")
    assert result.completeness is UsageCompleteness.UNAVAILABLE


def test_anthropic_zero_tokens_is_complete_not_missing():
    """Invariant #4: known-zero is not missing."""
    body = {"usage": {"input_tokens": 0, "output_tokens": 0}}
    result = normalize_json(ProviderFamily.ANTHROPIC_MESSAGES, body)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_output_tokens == 0


# ─── OpenAI Chat Completions ───────────────────────────────────────────────────


def test_openai_chat_json_with_cached_and_reasoning():
    body = {
        "usage": {
            "prompt_tokens": 1000,
            "completion_tokens": 200,
            "prompt_tokens_details": {"cached_tokens": 400},
            "completion_tokens_details": {"reasoning_tokens": 80},
        }
    }
    result = normalize_json(ProviderFamily.OPENAI_CHAT, body)
    assert result.tokens.total_input_tokens == 1000
    assert result.tokens.cache_read_tokens == 400
    assert result.tokens.uncached_input_tokens == 600  # prompt - cached
    assert result.tokens.total_output_tokens == 200
    assert result.tokens.reasoning_output_tokens == 80


def test_openai_chat_reasoning_is_subset_of_completion_not_additive():
    """Invariant #5. reasoning_tokens (80) is INCLUDED in completion_tokens (200)."""
    body = {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 200,
            "completion_tokens_details": {"reasoning_tokens": 80},
        }
    }
    result = normalize_json(ProviderFamily.OPENAI_CHAT, body)
    assert result.tokens.total_output_tokens == 200  # NOT 280
    assert result.tokens.reasoning_output_tokens == 80


def test_openai_chat_sse_with_include_usage_terminal_chunk():
    sse = (
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        b'data: {"choices":[{"delta":{"content":" there"}}]}\n\n'
        b'data: {"usage":{"prompt_tokens":50,"completion_tokens":10}}\n\n'
        b"data: [DONE]\n\n"
    )
    result = normalize_sse(ProviderFamily.OPENAI_CHAT, sse)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_input_tokens == 50


def test_openai_chat_sse_without_include_usage_is_unavailable_with_reason():
    """Distinguishable from truly interrupted (which has no chunks)."""
    sse = (
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        b"data: [DONE]\n\n"
    )
    result = normalize_sse(ProviderFamily.OPENAI_CHAT, sse)
    assert result.completeness is UsageCompleteness.UNAVAILABLE
    assert result.raw_usage.get("reason") == "include_usage_not_set"


def test_openai_chat_sse_interrupted_mid_stream():
    """Chunks arrived and usage came but no [DONE] — PARTIAL."""
    sse = (
        b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        b'data: {"usage":{"prompt_tokens":50,"completion_tokens":10}}\n\n'
    )
    result = normalize_sse(ProviderFamily.OPENAI_CHAT, sse)
    assert result.completeness is UsageCompleteness.PARTIAL


def test_openai_chat_json_missing_usage_is_unavailable():
    result = normalize_json(ProviderFamily.OPENAI_CHAT, {"choices": []})
    assert result.completeness is UsageCompleteness.UNAVAILABLE


# ─── OpenAI Responses ──────────────────────────────────────────────────────────


def test_openai_responses_json_with_cached_and_reasoning():
    body = {
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 200,
            "input_tokens_details": {"cached_tokens": 400},
            "output_tokens_details": {"reasoning_tokens": 80},
        }
    }
    result = normalize_json(ProviderFamily.OPENAI_RESPONSES, body)
    assert result.tokens.total_input_tokens == 1000
    assert result.tokens.cache_read_tokens == 400
    assert result.tokens.uncached_input_tokens == 600
    assert result.tokens.total_output_tokens == 200
    assert result.tokens.reasoning_output_tokens == 80


def test_openai_responses_sse_completed_event():
    sse = (
        b"event: response.created\n"
        b'data: {"type":"response.created","response":{}}\n\n'
        b"event: response.completed\n"
        b'data: {"type":"response.completed","response":{"usage":{"input_tokens":100,"output_tokens":25}}}\n\n'
    )
    result = normalize_sse(ProviderFamily.OPENAI_RESPONSES, sse)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_input_tokens == 100
    assert result.tokens.total_output_tokens == 25


def test_openai_responses_sse_incomplete_event_partial():
    sse = (
        b"event: response.incomplete\n"
        b'data: {"type":"response.incomplete","response":{"usage":{"input_tokens":100,"output_tokens":10}}}\n\n'
    )
    result = normalize_sse(ProviderFamily.OPENAI_RESPONSES, sse)
    assert result.completeness is UsageCompleteness.PARTIAL


# ─── LiteLLM ───────────────────────────────────────────────────────────────────


def test_litellm_delegates_to_openai_chat_but_labels_family():
    body = {
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_tokens_details": {"cached_tokens": 10},
        }
    }
    result = normalize_json(ProviderFamily.LITELLM, body)
    assert result.provider_family is ProviderFamily.LITELLM
    assert result.tokens.total_input_tokens == 100
    assert result.tokens.cache_read_tokens == 10
    assert result.tokens.uncached_input_tokens == 90


# ─── Cross-family invariants ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "family,payload",
    [
        (ProviderFamily.ANTHROPIC_MESSAGES, {"usage": {"input_tokens": 0, "output_tokens": 0}}),
        (ProviderFamily.OPENAI_CHAT, {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}),
        (ProviderFamily.OPENAI_RESPONSES, {"usage": {"input_tokens": 0, "output_tokens": 0}}),
        (ProviderFamily.LITELLM, {"usage": {"prompt_tokens": 0, "completion_tokens": 0}}),
    ],
)
def test_zero_usage_reports_complete_not_missing(family, payload):
    result = normalize_json(family, payload)
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_output_tokens == 0


@pytest.mark.parametrize(
    "family",
    [
        ProviderFamily.ANTHROPIC_MESSAGES,
        ProviderFamily.OPENAI_CHAT,
        ProviderFamily.OPENAI_RESPONSES,
        ProviderFamily.LITELLM,
    ],
)
def test_bytes_and_str_and_dict_all_accepted(family):
    if family is ProviderFamily.ANTHROPIC_MESSAGES:
        payload = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    else:
        payload = {"usage": {"prompt_tokens": 10, "completion_tokens": 5}} \
            if family is not ProviderFamily.OPENAI_RESPONSES \
            else {"usage": {"input_tokens": 10, "output_tokens": 5}}
    encoded = json.dumps(payload)
    a = normalize_json(family, payload)
    b = normalize_json(family, encoded)
    c = normalize_json(family, encoded.encode())
    assert a.tokens == b.tokens == c.tokens


def test_json_parity_across_openai_families():
    """Chat and Responses report the same numeric shape when both emit usage
    (they just use different field names)."""
    chat = normalize_json(
        ProviderFamily.OPENAI_CHAT,
        {"usage": {"prompt_tokens": 100, "completion_tokens": 20}},
    )
    resp = normalize_json(
        ProviderFamily.OPENAI_RESPONSES,
        {"usage": {"input_tokens": 100, "output_tokens": 20}},
    )
    assert chat.tokens.total_input_tokens == resp.tokens.total_input_tokens == 100
    assert chat.tokens.total_output_tokens == resp.tokens.total_output_tokens == 20


def test_sse_survives_chunk_boundary_within_json_data():
    """The whole point of the new parser — legacy line-by-line failed
    silently when a JSON payload split across TCP chunks."""
    parser_input = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
        b"event: message_delta\n"
        b'data: {"type":"message_delta","usage":{"output_tokens":50}}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )
    # Split mid-JSON payload
    from app.runtime.accounting.normalizers.anthropic_messages import (
        AnthropicMessagesNormalizer,
    )
    normalizer = AnthropicMessagesNormalizer()
    # Feed all at once for the ground-truth
    ground = normalizer.normalize_sse(parser_input)
    # Feed byte-by-byte (worst-case chunking) — result must match
    from app.runtime.accounting.normalizers.sse import SSEParser
    parser = SSEParser()
    start_usage: dict = {}
    delta_usage: dict = {}
    for i in range(len(parser_input)):
        for _evt in parser.feed(parser_input[i : i + 1]):
            payload = json.loads(_evt.data)
            if payload.get("type") == "message_start":
                start_usage = payload["message"]["usage"]
            elif payload.get("type") == "message_delta":
                delta_usage.update(payload["usage"])
    # Fed byte-by-byte we should have captured both usage payloads intact
    assert start_usage.get("input_tokens") == 100
    assert delta_usage.get("output_tokens") == 50
    assert ground.completeness is UsageCompleteness.COMPLETE
