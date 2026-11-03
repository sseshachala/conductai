"""SIEM pull feed: ``get_audit_feed`` MCP tool over ``audit_export.feed_page``."""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.modules.guard import audit_export as ax
from tests.test_audit_export import T0, WS, env, sqlite_table  # noqa: F401  (fixtures)

NOW = T0 + timedelta(hours=1)
SINCE = T0 - timedelta(minutes=1)


class _Ctx:
    workspace_id = WS
    clerk_user_id = "user_1"


@pytest.fixture
def feed_env(env):  # noqa: F811
    _, Session = env
    with patch("app.core.database.SessionLocal", Session), \
         patch("app.core.workspace_context.set_workspace_rls", lambda *a: None), \
         patch("app.core.auth.check_permission", return_value="security") as perm, \
         patch("app.modules.guard.routers.policies_helpers._write_audit") as audit:
        yield Session, perm, audit


def _page(Session, **kw):
    return ax.feed_page(Session(), uuid.UUID(WS), now=kw.pop("now", NOW), **kw)


def test_pages_cover_every_row_once_in_chain_order(feed_env):
    Session, _, _ = feed_env
    seen, cursor = [], None
    for _ in range(5):
        page = _page(Session, cursor=cursor, since=None if cursor else SINCE, limit=2)
        seen += [e["id"] for e in page["events"]]
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
    assert seen == [str(uuid.UUID(int=1000 + i)) for i in range(5)]
    assert _page(Session, cursor=cursor)["events"] == []


def test_feed_is_scoped_to_workspace_and_carries_hashes(feed_env):
    Session, _, _ = feed_env
    events = _page(Session, since=SINCE)["events"]
    assert {e["workspace_id"] for e in events} == {WS}
    assert all(e["entry_hash"] for e in events)


def test_recent_rows_are_held_back_until_the_lag_passes(feed_env):
    Session, _, _ = feed_env
    just_after_third = T0 + timedelta(minutes=2) + ax.FEED_LAG
    early = _page(Session, since=SINCE, now=just_after_third)
    assert len(early["events"]) == 3
    later = _page(Session, cursor=early["next_cursor"])
    assert [e["id"] for e in later["events"]] == [str(uuid.UUID(int=1003)), str(uuid.UUID(int=1004))]


def test_empty_page_keeps_cursor_position(feed_env):
    Session, _, _ = feed_env
    page = _page(Session, since=NOW)
    assert page["events"] == [] and page["has_more"] is False
    assert _page(Session, cursor=page["next_cursor"])["events"] == []


def test_invalid_cursor_rejected():
    with pytest.raises(ax.ExportRangeError):
        ax.decode_cursor("not-a-cursor")


def test_tool_records_feed_start_only_and_checks_permission(feed_env):
    from app.tools.registrations.lens.audit_export import get_audit_feed
    _, perm, audit = feed_env
    first = get_audit_feed(_Ctx(), since=SINCE.isoformat(), limit=2)
    assert first["kind"] == "audit_feed" and "next_cursor" in first
    assert audit.call_count == 1 and audit.call_args.args[2] == "audit.feed_start"
    get_audit_feed(_Ctx(), cursor=first["next_cursor"])
    assert audit.call_count == 1
    assert perm.call_args.kwargs["permission"] == "platform.audit_log.view"


def test_tool_refuses_without_permission(feed_env):
    from fastapi import HTTPException
    from app.tools.registrations.lens.audit_export import get_audit_feed
    _, perm, audit = feed_env
    perm.side_effect = HTTPException(status_code=403)
    res = get_audit_feed(_Ctx())
    assert res["status_code"] == 403 and "platform.audit_log.view" in res["error"]
    audit.assert_not_called()


def test_tool_rejects_bad_cursor(feed_env):
    from app.tools.registrations.lens.audit_export import get_audit_feed
    assert get_audit_feed(_Ctx(), cursor="garbage") == {"error": "invalid cursor"}


def test_registered_with_permission_and_read_only():
    from app.tools.registrations.lens.audit_export import TOOLS
    tool = next(t for t in TOOLS if t.name == "get_audit_feed")
    assert tool.permission == "platform.audit_log.view"
    assert tool.annotations.read_only is True
