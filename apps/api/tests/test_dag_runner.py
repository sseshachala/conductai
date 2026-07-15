"""Tests for dag_runner: topo sort, skip logic, retry, exceptions."""
import pytest

from app.runtime.dag_runner import _topological_sort, _find_skipped_blocks, _with_retry
from app.runtime.exceptions import ApprovalRequired, ClarificationRequired


def _node(id_: str, type_: str = "brain") -> dict:
    return {"id": id_, "data": {"type": type_}}


def _edge(src: str, tgt: str, handle: str = "pass") -> dict:
    return {"source": src, "target": tgt, "sourceHandle": handle}


# ── _topological_sort ─────────────────────────────────────────────────────────

def test_topo_linear_chain():
    nodes = [_node("a"), _node("b"), _node("c")]
    edges = [_edge("a", "b"), _edge("b", "c")]
    order = _topological_sort(nodes, edges)
    assert [n["id"] for n in order] == ["a", "b", "c"]


def test_topo_no_edges_any_order():
    nodes = [_node("x"), _node("y")]
    order = _topological_sort(nodes, edges=[])
    assert {n["id"] for n in order} == {"x", "y"}


def test_topo_diamond():
    # a → b, a → c, b → d, c → d
    nodes = [_node("a"), _node("b"), _node("c"), _node("d")]
    edges = [_edge("a", "b"), _edge("a", "c"), _edge("b", "d"), _edge("c", "d")]
    order = _topological_sort(nodes, edges)
    ids = [n["id"] for n in order]
    assert ids[0] == "a"
    assert ids[-1] == "d"
    assert set(ids[1:3]) == {"b", "c"}


def test_topo_cycle_raises():
    nodes = [_node("a"), _node("b")]
    edges = [_edge("a", "b"), _edge("b", "a")]
    with pytest.raises(RuntimeError, match="cycle"):
        _topological_sort(nodes, edges)


def test_topo_single_node():
    order = _topological_sort([_node("only")], [])
    assert len(order) == 1


# ── _find_skipped_blocks ──────────────────────────────────────────────────────

def test_skip_no_logic_routes_skips_nothing():
    nodes = [_node("a"), _node("b")]
    edges = [_edge("a", "b")]
    assert _find_skipped_blocks(nodes, edges, {}) == set()


def test_skip_logic_block_fail_branch():
    # logic → pass: b, fail: c
    nodes = [_node("logic"), _node("b"), _node("c")]
    edges = [
        _edge("logic", "b", handle="pass"),
        _edge("logic", "c", handle="fail"),
    ]
    skipped = _find_skipped_blocks(nodes, edges, {"logic": "pass"})
    assert "c" in skipped
    assert "b" not in skipped


def test_skip_convergent_path_not_skipped():
    # logic → pass: b, fail: c; both → d
    nodes = [_node("logic"), _node("b"), _node("c"), _node("d")]
    edges = [
        _edge("logic", "b", handle="pass"),
        _edge("logic", "c", handle="fail"),
        _edge("b", "d"),
        _edge("c", "d"),
    ]
    skipped = _find_skipped_blocks(nodes, edges, {"logic": "pass"})
    assert "c" in skipped
    assert "d" not in skipped  # reachable via b → d


# ── _with_retry ───────────────────────────────────────────────────────────────

def test_retry_succeeds_first_try():
    calls = []
    def fn():
        calls.append(1)
        return "ok"
    result = _with_retry(fn, {"max": 3})
    assert result == "ok"
    assert len(calls) == 1


def test_retry_retries_on_tool_error():
    calls = []
    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise Exception("transient")
        return "ok"
    result = _with_retry(fn, {"max": 3, "backoff": "fixed", "on": ["tool_error"]})
    assert result == "ok"
    assert len(calls) == 3


def test_retry_exhausted_raises():
    def fn():
        raise Exception("always fails")
    with pytest.raises(Exception, match="always fails"):
        _with_retry(fn, {"max": 2, "backoff": "fixed", "on": ["tool_error"]})


def test_retry_no_retry_on_approval_required():
    calls = []
    def fn():
        calls.append(1)
        raise ApprovalRequired("block1")
    with pytest.raises(ApprovalRequired):
        _with_retry(fn, {"max": 5, "on": ["tool_error"]})
    assert len(calls) == 1  # not retried


def test_retry_no_retry_on_clarification_required():
    calls = []
    def fn():
        calls.append(1)
        raise ClarificationRequired("block1", "what do you mean?")
    with pytest.raises(ClarificationRequired):
        _with_retry(fn, {"max": 5, "on": ["tool_error"]})
    assert len(calls) == 1


def test_retry_no_retry_on_runtime_error():
    calls = []
    def fn():
        calls.append(1)
        raise RuntimeError("guard block")
    with pytest.raises(RuntimeError):
        _with_retry(fn, {"max": 5, "on": ["tool_error"]})
    assert len(calls) == 1


# ── exceptions module ─────────────────────────────────────────────────────────

def test_exceptions_importable_from_exceptions_module():
    from app.runtime.exceptions import ApprovalRequired, ClarificationRequired
    ar = ApprovalRequired("b1", "needs approval")
    assert ar.block_id == "b1"
    cr = ClarificationRequired("b2", "ambiguous task")
    assert cr.block_id == "b2"
    assert cr.question == "ambiguous task"
