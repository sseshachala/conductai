"""Parallel dispatch helper — LLM tool_use blocks run concurrently while
preserving input order in the returned results.
"""
from __future__ import annotations

import json
import time
import threading

from app.runtime.llm_client import LLMToolUseBlock
from app.runtime.tool_dispatch import dispatch_tool_blocks


def _block(name: str, id_: str = "id", inp: dict | None = None) -> LLMToolUseBlock:
    return LLMToolUseBlock(id=id_, name=name, input=inp or {})


def test_empty_blocks_returns_empty_list():
    calls = []

    def _disp(name, args):
        calls.append(name)
        return "unused"

    assert dispatch_tool_blocks([], _disp) == []
    assert calls == []


def test_single_block_fast_path_no_pool():
    """One block skips the pool — verified by checking we execute on the
    caller thread (no worker thread spawn)."""
    caller_thread = threading.current_thread().ident
    seen = {}

    def _disp(name, args):
        seen["thread"] = threading.current_thread().ident
        return f"result_for_{name}"

    result = dispatch_tool_blocks([_block("a", "call_1", {"x": 1})], _disp)

    assert result == [("call_1", "result_for_a")]
    assert seen["thread"] == caller_thread, "single-block path must not spawn a worker"


def test_multiple_blocks_run_in_parallel():
    """3 blocks that each sleep 200ms complete in ~200ms, not ~600ms."""
    def _slow(name, args):
        time.sleep(0.2)
        return f"result_for_{name}"

    blocks = [_block("a", "id1"), _block("b", "id2"), _block("c", "id3")]

    start = time.monotonic()
    result = dispatch_tool_blocks(blocks, _slow)
    elapsed = time.monotonic() - start

    assert len(result) == 3
    assert elapsed < 0.5, f"parallel execution should finish under 0.5s, took {elapsed:.3f}s"


def test_result_order_matches_input_order_regardless_of_completion_order():
    """Preserve input order even if the third block finishes first (fast) and
    the first block finishes last (slow) — LLM tool_result correlation is
    positional in some clients."""
    def _variable(name, args):
        # sleep_ms comes from args so we can force wildly different durations
        args_d = json.loads(args)
        time.sleep(args_d.get("sleep_s", 0))
        return f"result_for_{name}"

    blocks = [
        _block("slow", "id1", {"sleep_s": 0.3}),
        _block("mid", "id2", {"sleep_s": 0.1}),
        _block("fast", "id3", {"sleep_s": 0.0}),
    ]

    result = dispatch_tool_blocks(blocks, _variable)

    assert [r[0] for r in result] == ["id1", "id2", "id3"]
    assert [r[1] for r in result] == ["result_for_slow", "result_for_mid", "result_for_fast"]


def test_args_json_serialisation():
    """dispatcher receives args as JSON string built from block.input dict."""
    captured = []

    def _capture(name, args):
        captured.append(args)
        return "ok"

    dispatch_tool_blocks(
        [_block("get_x", "id1", {"limit": 5, "filter": "recent"})],
        _capture,
    )

    parsed = json.loads(captured[0])
    assert parsed == {"limit": 5, "filter": "recent"}


def test_dispatcher_exception_propagates():
    """If any dispatcher raises, the exception surfaces to the caller (not
    silently swallowed). Contract choice: let the caller decide how to
    react — matching the legacy serial loop's behaviour."""
    def _boom(name, args):
        raise RuntimeError(f"dispatcher failed for {name}")

    try:
        dispatch_tool_blocks([_block("a", "id1"), _block("b", "id2")], _boom)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "dispatcher failed for" in str(exc)


def test_max_workers_cap():
    """Explicit max_workers below block count still returns all results."""
    def _disp(name, args):
        return f"result_for_{name}"

    blocks = [_block(f"tool_{i}", f"id{i}") for i in range(10)]
    result = dispatch_tool_blocks(blocks, _disp, max_workers=2)

    assert len(result) == 10
    assert [r[0] for r in result] == [f"id{i}" for i in range(10)]
