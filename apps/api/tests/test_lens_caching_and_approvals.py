"""Tests for Lens caching + approvals-tool broadening (2026-08-28 follow-up to #1347).

Post epic #1655: tools migrated from Executor to top-level free functions
in lens/ops.py. Tests patch app.core.database.SessionLocal to inject a
mock DB, since the tools now open their own session.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.tools.registrations.lens.ops import list_pending_approvals

# Import llm_client first so its re-exports resolve before we touch adapters.
import app.runtime.llm_client  # noqa: F401


class _Ctx:
    workspace_id = "00000000-0000-0000-0000-000000000001"


def _fake_db_with_query():
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = []
    fake_db = MagicMock()
    fake_db.query.return_value = fake_query
    return fake_db, fake_query


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
    fake_db, fake_query = _fake_db_with_query()
    with patch("app.core.database.SessionLocal", return_value=fake_db):
        result = list_pending_approvals(_Ctx(), status="all", since="today", limit=10)
    assert result == []
    # workspace_id + since (status skipped for "all") = 2 filter calls
    assert fake_query.filter.call_count == 2


def test_list_pending_approvals_supports_iso_date():
    """since='2026-08-28' parses cleanly and applies a filter."""
    fake_db, fake_query = _fake_db_with_query()
    with patch("app.core.database.SessionLocal", return_value=fake_db):
        list_pending_approvals(_Ctx(), status="pending", since="2026-08-28")
    # workspace_id + status + since = 3 filter calls
    assert fake_query.filter.call_count == 3


def test_list_pending_approvals_invalid_since_is_ignored():
    """Malformed since string should not crash — silently skip the filter."""
    fake_db, fake_query = _fake_db_with_query()
    with patch("app.core.database.SessionLocal", return_value=fake_db):
        list_pending_approvals(_Ctx(), status="pending", since="garbage")
    # workspace_id + status only; since dropped silently
    assert fake_query.filter.call_count == 2
