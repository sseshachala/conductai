"""
Unit tests for LLM response cache — #642 durable state.

Test 1: cache hit — _cache_get returns cached data when Redis has a value.
Test 2: cache miss — _cache_get returns None, _cache_set writes to Redis with correct key/TTL.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage
from app.runtime.blocks.brain_block import _cache_key, _cache_get, _cache_set, _LLM_CACHE_TTL


def _make_response(text: str = "ok") -> LLMResponse:
    return LLMResponse(
        content=[LLMTextBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=10, output_tokens=5),
        cost_usd=0.0001,
        _raw_content=[{"type": "text", "text": text}],
    )


# ── Test 1: cache hit — llm.create() would not be needed ─────────────────────

def test_cache_hit_returns_cached_response():
    run_id, block_id, turn = "run-123", "block-abc", 0
    cached = _make_response("cached answer")

    fake_redis = MagicMock()
    fake_redis.get.return_value = json.dumps(cached.to_cache_dict())

    result = _cache_get(run_id, block_id, turn, _r=fake_redis)

    assert result is not None
    fake_redis.get.assert_called_once_with(_cache_key(run_id, block_id, turn))

    restored = LLMResponse.from_cache_dict(result)
    assert restored.content[0].text == "cached answer"
    assert restored.stop_reason == "end_turn"
    assert restored.usage.input_tokens == 10


# ── Test 2: cache miss writes response to Redis ────────────────────────────────

def test_cache_miss_writes_to_redis():
    run_id, block_id, turn = "run-456", "block-xyz", 0
    response = _make_response("fresh answer")

    fake_redis = MagicMock()
    fake_redis.get.return_value = None

    # Miss
    result = _cache_get(run_id, block_id, turn, _r=fake_redis)
    assert result is None

    # Simulate LLM call then write to cache
    _cache_set(run_id, block_id, turn, response.to_cache_dict(), _r=fake_redis)

    key = _cache_key(run_id, block_id, turn)
    fake_redis.setex.assert_called_once()
    call_key, call_ttl, call_payload = fake_redis.setex.call_args[0]
    assert call_key == key
    assert call_ttl == _LLM_CACHE_TTL  # 86400s / 24h
    stored = json.loads(call_payload)
    assert stored["content"][0]["text"] == "fresh answer"
    assert stored["stop_reason"] == "end_turn"

    # Subsequent read returns the stored value
    fake_redis.get.return_value = call_payload
    result2 = _cache_get(run_id, block_id, turn, _r=fake_redis)
    assert LLMResponse.from_cache_dict(result2).content[0].text == "fresh answer"


# ── Serialization round-trip ──────────────────────────────────────────────────

def test_llm_response_roundtrip():
    original = _make_response("roundtrip")
    restored = LLMResponse.from_cache_dict(original.to_cache_dict())
    assert restored.content[0].text == "roundtrip"
    assert restored.stop_reason == original.stop_reason
    assert restored.usage.output_tokens == original.usage.output_tokens
    assert restored.cost_usd == original.cost_usd
    assert restored._raw_content == original._raw_content
