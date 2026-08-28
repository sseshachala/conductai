"""Test get_recent_events now accepts since='today' and returns id for link column."""
from __future__ import annotations

from unittest.mock import MagicMock


def test_get_recent_events_since_today_normalises_to_utc_midnight():
    from datetime import datetime, timezone
    from app.modules.glens.executor import Executor

    executor = Executor.__new__(Executor)
    executor.workspace_id = "00000000-0000-0000-0000-000000000001"

    fake_row = MagicMock()
    fake_row.id = "aaaa"
    fake_row.ts = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    fake_row.decision = "blocked"
    fake_row.user_email = "u@example.com"
    fake_row.ai_tool = "claude-code"
    fake_row.rule_id = "no-pii"
    fake_row.tool_name = "bash"

    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = [fake_row]

    executor.db = MagicMock()
    executor.db.query.return_value = fake_query
    # _org_ws_subquery uses .execute, patch that too
    from unittest.mock import patch
    with patch("app.modules.glens.executor._org_ws_subquery", return_value=[executor.workspace_id]):
        rows = executor._tool_get_recent_events(decision="blocked", since="today", limit=5)

    assert rows == [{
        "id": "aaaa",
        "ts": "2026-08-28T10:00:00+00:00",
        "decision": "blocked",
        "user_email": "u@example.com",
        "ai_tool": "claude-code",
        "rule_id": "no-pii",
        "tool_name": "bash",
    }]


def test_get_recent_events_iso_since_still_works():
    from unittest.mock import patch
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

    with patch("app.modules.glens.executor._org_ws_subquery", return_value=[executor.workspace_id]):
        executor._tool_get_recent_events(since="2026-08-28T00:00:00Z")
    # workspace_id + since = 2 filter calls (decision + rule_id skipped)
    assert fake_query.filter.call_count == 2
