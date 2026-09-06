"""Test get_recent_events accepts since='today' and returns id for link column.

Post epic #1655: tool migrated from Executor to top-level function in
lens/guard_core.py. Tests now patch guard_core.SessionLocal and
_org_ws_subquery to isolate the function under test.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


class _Ctx:
    workspace_id = "00000000-0000-0000-0000-000000000001"


def _fake_db_with_rows(rows):
    fake_query = MagicMock()
    fake_query.filter.return_value = fake_query
    fake_query.order_by.return_value = fake_query
    fake_query.limit.return_value = fake_query
    fake_query.all.return_value = rows
    fake_db = MagicMock()
    fake_db.query.return_value = fake_query
    return fake_db, fake_query


def test_get_recent_events_since_today_normalises_to_utc_midnight():
    from datetime import datetime, timezone
    from app.tools.registrations.lens.guard_core import get_recent_events

    fake_row = MagicMock()
    fake_row.id = "aaaa"
    fake_row.ts = datetime(2026, 8, 28, 10, 0, tzinfo=timezone.utc)
    fake_row.decision = "blocked"
    fake_row.user_email = "u@example.com"
    fake_row.ai_tool = "claude-code"
    fake_row.rule_id = "no-pii"
    fake_row.tool_call = "bash"

    fake_db, _ = _fake_db_with_rows([fake_row])
    with patch("app.core.database.SessionLocal", return_value=fake_db), \
         patch("app.tools.registrations.lens.guard_core._org_ws_subquery", return_value=[_Ctx.workspace_id]):
        rows = get_recent_events(_Ctx(), decision="blocked", since="today", limit=5)

    assert rows == [{
        "id": "aaaa",
        "ts": "2026-08-28T10:00:00+00:00",
        "decision": "blocked",
        "user_email": "u@example.com",
        "ai_tool": "claude-code",
        "rule_id": "no-pii",
        "tool_call": "bash",
    }]


def test_get_recent_events_iso_since_still_works():
    from app.tools.registrations.lens.guard_core import get_recent_events

    fake_db, fake_query = _fake_db_with_rows([])
    with patch("app.core.database.SessionLocal", return_value=fake_db), \
         patch("app.tools.registrations.lens.guard_core._org_ws_subquery", return_value=[_Ctx.workspace_id]):
        get_recent_events(_Ctx(), since="2026-08-28T00:00:00Z")
    # workspace_id + since = 2 filter calls (decision + rule_id skipped)
    assert fake_query.filter.call_count == 2
