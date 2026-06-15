"""
Integration unit tests for LLM response cache — #642.

Test 1: cache hit  — _execute_brain does NOT call llm.create() when Redis has a cached response.
Test 2: cache miss — _execute_brain calls llm.create() once and writes the response to Redis.

Uses the single-shot (non-agentic) Brain block path to keep setup minimal.
Stubs app.runtime.executor via sys.modules to avoid the SQLAlchemy dependency.
"""
from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

# ── Stub executor before brain_block imports it ───────────────────────────────
_executor_stub = ModuleType("app.runtime.executor")
_executor_stub._emit = MagicMock()
_executor_stub._write_trace = MagicMock()
_executor_stub._resolve_refs = lambda state, _block: state
_executor_stub._resolve_remote_host = lambda *a, **kw: None
_executor_stub._summarise_tool_call = lambda *a, **kw: ""
_executor_stub.ClarificationRequired = type("ClarificationRequired", (Exception,), {"block_id": None, "question": None})
sys.modules.setdefault("app.runtime.executor", _executor_stub)

from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage  # noqa: E402
from app.runtime.blocks.brain_block import _cache_key, _LLM_CACHE_TTL  # noqa: E402


# ── Shared fixtures ────────────────────────────────────────────────────────────

RUN_ID   = "run-test-001"
BLOCK_ID = "brain-1"

_BLOCK = {
    "id": BLOCK_ID,
    "type": "brain",
    "data": {
        "label": "test brain",
        "isAgentic": False,
        "goal": "say hello",
        "outputDescription": "greeting",
    },
}

_ARTIFACTS = {
    BLOCK_ID: {
        "system_prompt": "You are a test assistant.",
        "is_agentic": False,
    }
}


def _fake_llm_response(text: str = "hello") -> LLMResponse:
    return LLMResponse(
        content=[LLMTextBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=10, output_tokens=3),
        cost_usd=0.00005,
        _raw_content=[{"type": "text", "text": text}],
    )


def _fake_redis(cached_payload: str | None) -> MagicMock:
    r = MagicMock()
    r.get.return_value = cached_payload
    return r


# ── Test 1: cache hit — llm.create() is NOT called ───────────────────────────

def test_cache_hit_skips_llm_create():
    cached = _fake_llm_response("cached hello")
    redis_instance = _fake_redis(json.dumps(cached.to_cache_dict()))

    mock_llm = MagicMock()

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_instance),
    ):
        from app.runtime.blocks.brain_block import _execute_brain
        result = _execute_brain(
            block=_BLOCK,
            state={"input": "hi"},
            compiled_artifacts=_ARTIFACTS,
            run_id=RUN_ID,
            block_id=BLOCK_ID,
        )

    mock_llm.create.assert_not_called()
    assert "cached hello" in str(result.get("output", ""))


# ── Test 2: cache miss — llm.create() called once, result written to Redis ───

def test_cache_miss_calls_llm_and_writes_cache():
    redis_instance = _fake_redis(None)  # miss

    fresh = _fake_llm_response("fresh hello")
    mock_llm = MagicMock()
    mock_llm.create.return_value = fresh

    with (
        patch("app.runtime.blocks.brain_block.AnthropicClient", return_value=mock_llm),
        patch("app.runtime.blocks.brain_block._get_redis", return_value=redis_instance),
    ):
        from app.runtime.blocks.brain_block import _execute_brain
        _execute_brain(
            block=_BLOCK,
            state={"input": "hi"},
            compiled_artifacts=_ARTIFACTS,
            run_id=RUN_ID,
            block_id=BLOCK_ID,
        )

    mock_llm.create.assert_called_once()

    redis_instance.setex.assert_called_once()
    key, ttl, payload = redis_instance.setex.call_args[0]
    assert key == _cache_key(RUN_ID, BLOCK_ID, 0)
    assert ttl == _LLM_CACHE_TTL
    stored = json.loads(payload)
    assert stored["content"][0]["text"] == "fresh hello"
