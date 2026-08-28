"""Tests for Lens caching + approvals-tool broadening (2026-08-28 follow-up to #1347)."""
from __future__ import annotations

from unittest.mock import MagicMock

# Import llm_client first so its re-exports resolve before we touch adapters.
import app.runtime.llm_client  # noqa: F401


def test_adapter_default_enables_cache_system():
    """Prompt caching is on by default at the adapter level — every caller
    of LLMClient.create() gets it without opting in, so brain_block, Lens,
    conductgen, sdd, workflows, team_memory all cache automatically on
    Anthropic (silent no-op on other providers)."""
    import inspect
    from app.runtime.llm_client import LLMClient, AnthropicClient, OpenAIClient, PerplexityClient

    for cls in (AnthropicClient, OpenAIClient, PerplexityClient, LLMClient):
        sig = inspect.signature(cls.create)
        assert sig.parameters["cache_system"].default is True, (
            f"{cls.__name__}.create must default cache_system=True"
        )


def test_list_pending_approvals_supports_since_today():
    """since='today' should filter created_at >= UTC start-of-day."""
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
    # workspace_id + since (status skipped for "all") = 2 filter calls
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
    # workspace_id + status + since = 3 filter calls
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
