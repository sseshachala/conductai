"""Tests for Lens caching + approvals-tool broadening (2026-08-28 follow-up to #1347)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def test_guarded_client_call_enables_cache_system():
    """cache_system=True must flow into client.create so Anthropic caches
    the system + tools block; OpenAI/Perplexity adapters no-op silently."""
    from app.guard.gateway import guarded_client_call

    captured = {}
    fake_client = MagicMock()
    fake_client.create.side_effect = lambda **kw: (captured.update(kw), MagicMock(usage=MagicMock(input_tokens=1, output_tokens=1)))[1]

    with patch("app.guard.policy.evaluate_composed") as _eval, \
         patch("app.guard.gateway._record_audit"):
        from app.guard.policy_types import PolicyAction, PolicyDecision
        _eval.return_value = PolicyDecision(action=PolicyAction.ALLOW, source="test")
        guarded_client_call(
            client=fake_client,
            workspace_id="ws-1",
            provider="anthropic",
            model="claude-sonnet-4-6",
            messages=[{"role": "user", "content": "hi"}],
            system="You are helpful.",
            tools=[{"name": "t", "description": "x", "input_schema": {"type": "object", "properties": {}}}],
        )

    assert captured.get("cache_system") is True


def test_list_pending_approvals_supports_since_today():
    """since='today' should filter created_at >= UTC start-of-day.
    Verifies the SQLAlchemy filter chain runs cleanly with the new param."""
    from app.modules.glens.executor import Executor

    executor = Executor.__new__(Executor)
    executor.workspace_id = "00000000-0000-0000-0000-000000000001"

    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []

    executor.db = MagicMock()
    executor.db.query.return_value = fake_query

    result = executor._tool_list_pending_approvals(status="all", since="today", limit=10)
    assert result == []
    # 3 filter calls: workspace_id, (status skipped for "all"), since
    # workspace_id + since = 2 filters when status=all
    assert fake_query.filter.call_count == 2


def test_list_pending_approvals_supports_iso_date():
    """since='2026-08-28' parses cleanly and applies a filter."""
    from app.modules.glens.executor import Executor

    executor = Executor.__new__(Executor)
    executor.workspace_id = "00000000-0000-0000-0000-000000000001"
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    executor.db = MagicMock()
    executor.db.query.return_value = fake_query

    executor._tool_list_pending_approvals(status="pending", since="2026-08-28")
    # workspace_id + status + since = 3 filters
    assert fake_query.filter.call_count == 3


def test_list_pending_approvals_invalid_since_is_ignored():
    """Malformed since string should not crash — silently skip the filter."""
    from app.modules.glens.executor import Executor

    executor = Executor.__new__(Executor)
    executor.workspace_id = "00000000-0000-0000-0000-000000000001"
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    executor.db = MagicMock()
    executor.db.query.return_value = fake_query

    executor._tool_list_pending_approvals(status="pending", since="garbage")
    # workspace_id + status only; since dropped silently
    assert fake_query.filter.call_count == 2
