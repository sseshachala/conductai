"""Unit tests for list_my_runs + list_runs_in_session Lens tools (#1480 PR 8).

Focus: registration + input/error paths. DB-touching query paths auto-skip
without Postgres, same as the sibling test_run_tools.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.tools import registrations as _tool_registrations  # noqa: F401 populate
from app.tools.registrations.lens.runs import list_my_runs, list_runs_in_session
from app.tools.registry import default_registry


# ── Registration ───────────────────────────────────────────────────────────

def test_list_my_runs_registered() -> None:
    tool = default_registry.get("list_my_runs")
    assert tool is not None
    assert "lens" in tool.tags
    assert tool.annotations.read_only is True


def test_list_runs_in_session_registered() -> None:
    tool = default_registry.get("list_runs_in_session")
    assert tool is not None
    assert "lens" in tool.tags
    assert tool.annotations.read_only is True


# ── list_my_runs input validation ─────────────────────────────────────────

def test_list_my_runs_rejects_missing_user() -> None:
    ctx = SimpleNamespace(workspace_id="ws-1", clerk_user_id=None)
    out = list_my_runs(ctx)
    assert "error" in out
    assert "real user" in out["error"]


def test_list_my_runs_rejects_system_user() -> None:
    """system:lens is the actor's synthetic id, not a real user — the tool
    is 'what did I run', not 'what did the agent run'."""
    ctx = SimpleNamespace(workspace_id="ws-1", clerk_user_id="system:lens")
    out = list_my_runs(ctx)
    assert "error" in out
    assert "real user" in out["error"]


# ── list_runs_in_session input validation ─────────────────────────────────

def test_list_runs_in_session_requires_session() -> None:
    ctx = SimpleNamespace(workspace_id="ws-1", session_id=None)
    out = list_runs_in_session(ctx)
    assert "error" in out
    assert "session_id" in out["error"]


def test_list_runs_in_session_rejects_non_uuid() -> None:
    ctx = SimpleNamespace(workspace_id="ws-1", session_id="not-a-uuid")
    out = list_runs_in_session(ctx, session_id="not-a-uuid")
    assert "error" in out
    assert "UUID" in out["error"]


def test_list_runs_in_session_defaults_to_ctx_session_id() -> None:
    """When no session_id arg passed, tool reads ctx.session_id.

    We stub SessionLocal + query so no DB is required — the goal is
    to prove the ctx fallback path resolves the session_id correctly
    before the query attempts to run.
    """
    ctx = SimpleNamespace(
        workspace_id="00000000-0000-0000-0000-000000000000",
        session_id="11111111-1111-1111-1111-111111111111",
    )
    with patch("app.core.database.SessionLocal") as mock_sl, \
         patch("app.modules.glens.executor._org_ws_subquery", return_value=[]):
        mock_db = MagicMock()
        mock_db.query.return_value.join.return_value.join.return_value \
            .filter.return_value.filter.return_value.order_by.return_value \
            .limit.return_value.all.return_value = []
        mock_sl.return_value = mock_db
        out = list_runs_in_session(ctx)
    assert out == []  # empty list — no error, ctx fallback worked
