"""SIEM pull feed: ``get_audit_feed`` MCP tool over ``audit_export.feed_page``."""
from __future__ import annotations

import uuid
from datetime import timedelta
from unittest.mock import patch

import fakeredis
import pytest

from app.modules.guard import audit_export as ax
from tests.test_audit_export import T0, WS, env, sqlite_table  # noqa: F401  (fixtures)

NOW = T0 + timedelta(hours=1)
SINCE = T0 - timedelta(minutes=1)


_FAKE_REDIS = fakeredis.FakeRedis(decode_responses=True)


class _Ctx:
    workspace_id = WS
    clerk_user_id = "user_1"


@pytest.fixture
def feed_env(env):  # noqa: F811
    _, Session = env
    with patch("app.core.database.SessionLocal", Session), \
         patch("app.core.workspace_context.set_workspace_rls", lambda *a: None), \
         patch("app.core.auth.check_permission", return_value="security") as perm, \
         patch("app.modules.guard.routers.policies_helpers._write_audit") as audit, \
         patch.object(ax, "_status_redis", lambda: _FAKE_REDIS):
        _FAKE_REDIS.flushall()
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


# ── feed status ──────────────────────────────────────────────────────────────

def test_status_records_last_pull_and_lag(feed_env):
    Session, _, _ = feed_env
    page = _page(Session, since=SINCE, limit=2)
    ax.record_feed_pull(WS, "user_1", page, now=NOW, client=_FAKE_REDIS)
    status = ax.feed_status(WS, now=NOW + timedelta(minutes=1), client=_FAKE_REDIS)
    [c] = status["collectors"]
    cursor_ts, _ = ax.decode_cursor(page["next_cursor"])
    assert c["actor_id"] == "user_1" and c["last_page_events"] == 2 and c["stale"] is False
    assert c["lag_seconds"] == int((NOW + timedelta(minutes=1) - cursor_ts).total_seconds())


def test_status_marks_quiet_collector_stale_and_is_per_workspace(feed_env):
    Session, _, _ = feed_env
    ax.record_feed_pull(WS, "user_1", _page(Session, since=SINCE), now=NOW, client=_FAKE_REDIS)
    later = NOW + ax.FEED_STALE_AFTER + timedelta(seconds=1)
    assert ax.feed_status(WS, now=later, client=_FAKE_REDIS)["collectors"][0]["stale"] is True
    assert ax.feed_status(str(uuid.uuid4()), client=_FAKE_REDIS)["collectors"] == []


def test_status_unavailable_when_redis_down():
    class _Down:
        def hgetall(self, *_):
            raise ConnectionError("down")
    assert ax.feed_status(WS, client=_Down())["available"] is False
    ax.record_feed_pull(WS, "u", {"next_cursor": "bad"}, client=_Down())  # never raises


def test_tool_call_updates_status(feed_env):
    from app.tools.registrations.lens.audit_export import get_audit_feed, get_audit_feed_status
    get_audit_feed(_Ctx(), since=SINCE.isoformat(), limit=2)
    res = get_audit_feed_status(_Ctx())
    assert res["kind"] == "audit_feed_status"
    assert [c["actor_id"] for c in res["collectors"]] == ["user_1"]


def test_status_tool_requires_permission(feed_env):
    from fastapi import HTTPException

    from app.tools.registrations.lens.audit_export import get_audit_feed_status
    _, perm, _ = feed_env
    perm.side_effect = HTTPException(status_code=403)
    assert get_audit_feed_status(_Ctx())["status_code"] == 403
