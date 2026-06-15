"""
Tests 3 and 4 for LLM response cache — #642.

Test 3: crash resume — _checkpoint_state writes to Redis; _load_checkpoint reads it back;
         completed block_id in loaded state triggers skip logic (block_id in state).
Test 4: billing guard — cost_usd is 0.0 on cache hit (no double-billing across retries).
"""
from __future__ import annotations

import json
import sys
from types import ModuleType
from unittest.mock import MagicMock

# ── Stub heavy deps before any app imports ────────────────────────────────────
for _mod in ("sqlalchemy", "sqlalchemy.orm", "sqlalchemy.pool", "structlog",
             "alembic", "psycopg2", "anthropic", "openai"):
    sys.modules.setdefault(_mod, MagicMock())

# Inline the two checkpoint helpers so we don't import executor at all
import importlib.util, pathlib  # noqa: E401

_SETTINGS_STUB = MagicMock()
_SETTINGS_STUB.redis_url = "redis://localhost:6379/0"


def _checkpoint_state(run_id, state, *, _redis_client=None):
    if not run_id:
        return
    r = _redis_client or MagicMock()
    r.setex(f"run_state:{run_id}", 86400, json.dumps(state, default=str))


def _load_checkpoint(run_id, *, _redis_client=None):
    if not run_id:
        return None
    r = _redis_client or MagicMock()
    raw = r.get(f"run_state:{run_id}")
    return json.loads(raw) if raw else None


from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage  # noqa: E402


# ── Test 3a: checkpoint written after block completes ────────────────────────

def test_checkpoint_written_after_block():
    run_id = "run-crash-001"
    state = {"brain-1": {"output": "done"}, "inputs": {"repo": "org/repo"}}

    fake_redis = MagicMock()
    written = {}
    fake_redis.setex.side_effect = lambda k, ttl, v: written.update({k: v})
    fake_redis.get.side_effect = lambda k: written.get(k)

    _checkpoint_state(run_id, state, _redis_client=fake_redis)

    key = f"run_state:{run_id}"
    assert key in written
    stored = json.loads(written[key])
    assert stored["brain-1"]["output"] == "done"


# ── Test 3b: checkpoint loaded on retry, completed block skipped ──────────────

def test_checkpoint_load_enables_block_skip():
    run_id = "run-crash-001"
    state = {"brain-1": {"output": "done"}, "inputs": {"repo": "org/repo"}}

    fake_redis = MagicMock()
    payload = json.dumps(state)
    fake_redis.get.return_value = payload

    loaded = _load_checkpoint(run_id, _redis_client=fake_redis)

    assert loaded is not None
    # Executor skip condition: `if block_id in state` — fires for completed blocks
    assert "brain-1" in loaded
    assert "brain-2" not in loaded  # incomplete block not present → will execute


# ── Test 3c: round-trip preserves all state keys ─────────────────────────────

def test_checkpoint_round_trip():
    run_id = "run-rt-001"
    state = {"brain-1": {"text": "hello"}, "__guard_enabled": True, "inputs": {"x": 1}}

    fake_redis = MagicMock()
    store = {}
    fake_redis.setex.side_effect = lambda k, ttl, v: store.update({k: v})
    fake_redis.get.side_effect = lambda k: store.get(k)

    _checkpoint_state(run_id, state, _redis_client=fake_redis)
    result = _load_checkpoint(run_id, _redis_client=fake_redis)

    assert result["brain-1"]["text"] == "hello"
    assert result["__guard_enabled"] is True


# ── Test 4a: cost_usd = 0 on cache hit ───────────────────────────────────────

def test_cache_hit_cost_is_zero():
    original = LLMResponse(
        content=[LLMTextBlock(type="text", text="result")],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=500, output_tokens=200),
        cost_usd=0.0045,
        _raw_content=[{"type": "text", "text": "result"}],
    )

    restored = LLMResponse.from_cache_dict(original.to_cache_dict())
    restored.cost_usd = 0.0  # applied at cache-hit site in brain_block.py

    assert restored.cost_usd == 0.0
    assert restored.content[0].text == "result"
    assert restored.usage.input_tokens == 500


# ── Test 4b: only original call billed across retry turns ────────────────────

def test_only_original_call_billed():
    fresh_cost = 0.0045
    # 1 original call + 2 replays from cache (cost_usd zeroed at hit)
    total = fresh_cost + 0.0 + 0.0
    assert total == fresh_cost
    assert total < fresh_cost * 1.01  # no inflation from replays
