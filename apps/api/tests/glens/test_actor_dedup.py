"""#1470 — require_confirmation dedupes same-session re-proposals.

Key computation is stable per (tool, resolved_input) after stripping
underscore-prefixed private fields. Live-DB dedup is exercised on the
integration side; here we verify the pure key logic + the lookup filter.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.glens.actor.helpers import (
    _find_existing_pending,
    _idempotency_key,
)


# ── Key stability ────────────────────────────────────────────────────────────

def test_key_stable_for_same_input():
    a = _idempotency_key("run_workflow", {"workflow_id": "wf-1", "inputs": {"a": 1}})
    b = _idempotency_key("run_workflow", {"workflow_id": "wf-1", "inputs": {"a": 1}})
    assert a == b


def test_key_differs_by_tool_name():
    a = _idempotency_key("run_workflow", {"x": 1})
    b = _idempotency_key("decide_approval", {"x": 1})
    assert a != b


def test_key_differs_by_input_value():
    a = _idempotency_key("run_workflow", {"workflow_id": "wf-1"})
    b = _idempotency_key("run_workflow", {"workflow_id": "wf-2"})
    assert a != b


def test_key_ignores_underscore_fields():
    """Private fields like _warnings / _execute_result / _idem_key are
    computed post-facto and must not affect the key."""
    a = _idempotency_key("run_workflow", {"workflow_id": "wf-1"})
    b = _idempotency_key("run_workflow", {
        "workflow_id": "wf-1",
        "_warnings": ["Guard is disabled"],
        "_idem_key": "should-be-ignored",
        "_execute_result": {"run_id": "r1"},
    })
    assert a == b


def test_key_stable_across_dict_order():
    a = _idempotency_key("run_workflow", {"a": 1, "b": 2})
    b = _idempotency_key("run_workflow", {"b": 2, "a": 1})
    assert a == b


# ── Lookup filter ────────────────────────────────────────────────────────────

class _StubQuery:
    def __init__(self, rows):
        self._rows = rows
    def filter(self, *a, **kw): return self
    def order_by(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def all(self): return self._rows


def _make_db(rows):
    db = MagicMock()
    db.query.return_value = _StubQuery(rows)
    return db


def test_lookup_returns_row_with_matching_key():
    matching = SimpleNamespace(tool_input={"_idem_key": "abc123", "workflow_id": "wf-1"})
    db = _make_db([matching])
    out = _find_existing_pending(
        db,
        workspace_id="00000000-0000-0000-0000-000000000000",
        session_id="sess-xyz",
        tool_name="run_workflow",
        idem_key="abc123",
    )
    assert out is matching


def test_lookup_skips_row_with_different_key():
    other = SimpleNamespace(tool_input={"_idem_key": "different", "workflow_id": "wf-1"})
    db = _make_db([other])
    out = _find_existing_pending(
        db,
        workspace_id="00000000-0000-0000-0000-000000000000",
        session_id="sess-xyz",
        tool_name="run_workflow",
        idem_key="abc123",
    )
    assert out is None


def test_lookup_skips_row_with_no_key_stashed():
    """Legacy rows written before #1470 have no _idem_key. Should not match."""
    legacy = SimpleNamespace(tool_input={"workflow_id": "wf-1"})
    db = _make_db([legacy])
    out = _find_existing_pending(
        db,
        workspace_id="00000000-0000-0000-0000-000000000000",
        session_id="sess-xyz",
        tool_name="run_workflow",
        idem_key="abc123",
    )
    assert out is None


def test_lookup_returns_none_on_bad_workspace_uuid():
    db = _make_db([])
    out = _find_existing_pending(
        db,
        workspace_id="not-a-uuid",
        session_id="sess-xyz",
        tool_name="run_workflow",
        idem_key="abc",
    )
    assert out is None
