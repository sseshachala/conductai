"""Smoke tests for _get_spend_summary_inner.

These run without a real Postgres DB — they mock the ORM session just enough
to verify the function doesn't NameError, TypeError, or silently swallow bugs.

The key lesson from the July 2026 incident: the outer try/except Exception was
hiding NameError (missing `now`) and ProgrammingError (UUID vs text). These
tests catch that class of regression.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
import pytest


def _make_mock_db():
    """Return a SQLAlchemy Session mock that returns empty-but-valid results."""
    db = MagicMock()

    # Scalar aggregate queries (.one() / .scalar()) return safe zero values
    scalar_result = MagicMock()
    scalar_result.tokens_before = 0
    scalar_result.tokens_after = 0
    scalar_result.cost_before = 0.0
    scalar_result.cost_after = 0.0

    query_chain = MagicMock()
    query_chain.filter.return_value = query_chain
    query_chain.group_by.return_value = query_chain
    query_chain.order_by.return_value = query_chain
    query_chain.offset.return_value = query_chain
    query_chain.limit.return_value = query_chain
    query_chain.one.return_value = scalar_result
    query_chain.scalar.return_value = 0
    query_chain.all.return_value = []

    db.query.return_value = query_chain

    # Raw SQL execute (active_developers query)
    execute_result = MagicMock()
    execute_result.scalar.return_value = 0
    db.execute.return_value = execute_result

    return db


def _mock_org_ws(db, workspace_id):
    """Stub _org_ws_subquery to return an empty query (no workspace match needed)."""
    q = MagicMock()
    q.all.return_value = [("ef0a7e36-42a7-4968-9e6f-ee30d8e45383",)]
    q.filter.return_value = q
    return q


def test_inner_does_not_nameError():
    """_get_spend_summary_inner must not raise NameError for `now`."""
    from app.modules.guard.routers.spend import _get_spend_summary_inner

    db = _make_mock_db()
    with patch("app.modules.guard.routers.spend._org_ws_subquery", _mock_org_ws):
        result = _get_spend_summary_inner(db, "ef0a7e36-42a7-4968-9e6f-ee30d8e45383", None)

    assert result.events_today == 0
    assert result.hook_sessions == 0


def test_inner_returns_spend_summary_type():
    """Return type must be SpendSummary with expected fields."""
    from app.modules.guard.routers.spend import _get_spend_summary_inner, SpendSummary

    db = _make_mock_db()
    with patch("app.modules.guard.routers.spend._org_ws_subquery", _mock_org_ws):
        result = _get_spend_summary_inner(db, "ef0a7e36-42a7-4968-9e6f-ee30d8e45383", None)

    assert isinstance(result, SpendSummary)
    assert hasattr(result, "events_today")
    assert hasattr(result, "hook_sessions")
    assert hasattr(result, "sessions")
    assert hasattr(result, "by_developer")
    assert hasattr(result, "by_ai_tool")


def test_outer_reraises_programming_errors():
    """Non-operational errors (NameError, ProgrammingError) must NOT be swallowed."""
    from app.modules.guard.routers.spend import get_spend_summary
    from sqlalchemy.exc import OperationalError

    db = MagicMock()
    db.query.side_effect = RuntimeError("column does not exist")

    # Should propagate, not silently return zeros
    with pytest.raises(RuntimeError, match="column does not exist"):
        with patch("app.modules.guard.routers.spend._org_ws_subquery", _mock_org_ws):
            get_spend_summary(db=db, workspace_id="ef0a7e36-42a7-4968-9e6f-ee30d8e45383", month=None)


def test_outer_catches_operational_error():
    """OperationalError (DB unreachable) must return zeros gracefully."""
    from app.modules.guard.routers.spend import get_spend_summary
    from sqlalchemy.exc import OperationalError

    db = MagicMock()
    db.query.side_effect = OperationalError("connection refused", None, None)

    with patch("app.modules.guard.routers.spend._org_ws_subquery", _mock_org_ws):
        result = get_spend_summary(db=db, workspace_id="ef0a7e36-42a7-4968-9e6f-ee30d8e45383", month=None)

    assert result.events_today == 0  # graceful fallback
