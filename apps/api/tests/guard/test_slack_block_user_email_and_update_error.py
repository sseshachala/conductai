"""Two Slack-surface regressions on hook events:

1. Block/warn Slack cards were rendering ``User: user_xxx`` (raw Clerk id)
   because ``_bg_slack_notify`` fell back to ``clerk_user_id`` without
   resolving it to an email first.

2. ``update_approval_message`` swallowed ``chat.update`` errors — Approve/
   Reject buttons stayed visible after a click because the update failed
   silently (missing_scope / not_in_channel / etc.) with no log line to
   diagnose from.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_bg_slack_notify_resolves_clerk_id_to_email(monkeypatch):
    from app.modules.guard.routers import events as _events

    captured = {}

    def _fake_notify(_db, _ws, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(_events, "notify_guard_block", _fake_notify)
    monkeypatch.setattr(_events, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(
        "app.core.auth.get_clerk_user_email",
        lambda cid: "sudhi@b2bsphere.com" if cid == "user_3FaVu74iF3CN1ou9AUDBcuBx1Oq" else None,
    )

    _events._bg_slack_notify(
        workspace_id_str="11111111-1111-1111-1111-111111111111",
        decision="blocked",
        notify_on_block=True,
        alert_channel="#guard",
        user_email=None,   # hook events often omit this — the bug's trigger
        clerk_user_id="user_3FaVu74iF3CN1ou9AUDBcuBx1Oq",
        ai_tool="claude-code",
        rule_id="no-env-read",
        rule_message=None,
    )

    assert captured["user_email"] == "sudhi@b2bsphere.com", (
        "hook Slack block still shows raw Clerk id instead of email"
    )


def test_bg_slack_notify_falls_back_to_clerk_id_when_lookup_fails(monkeypatch):
    """When Clerk lookup returns None the Slack card is still useful — it
    just falls back to the raw id rather than posting an empty ``User:`` line."""
    from app.modules.guard.routers import events as _events

    captured = {}
    monkeypatch.setattr(_events, "notify_guard_block", lambda _db, _ws, **kw: captured.update(kw))
    monkeypatch.setattr(_events, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr("app.core.auth.get_clerk_user_email", lambda cid: None)

    _events._bg_slack_notify(
        workspace_id_str="11111111-1111-1111-1111-111111111111",
        decision="blocked",
        notify_on_block=True,
        alert_channel="#guard",
        user_email=None,
        clerk_user_id="user_UNRESOLVABLE",
        ai_tool="claude-code",
        rule_id="test",
        rule_message=None,
    )
    assert captured["user_email"] == "user_UNRESOLVABLE"


def test_update_approval_message_logs_slack_error(monkeypatch, capsys):
    from app.runtime.integrations import slack as _slack

    class _FakeResp:
        def json(self):
            return {"ok": False, "error": "missing_scope", "needed": "chat:write", "provided": "commands"}

    monkeypatch.setattr(_slack.httpx, "post", lambda *a, **k: _FakeResp())

    logged = []
    monkeypatch.setattr(_slack.log, "warning", lambda event, **kw: logged.append((event, kw)))

    result = _slack.update_approval_message(
        token="xoxb-fake", channel="C123", ts="1.000", decision="approved", approver="sudhi",
    )

    assert result["ok"] is False
    assert result["error"] == "missing_scope"
    assert logged and logged[0][0] == "slack.chat_update_failed", (
        "chat.update failure must be logged so ops can diagnose why Approve looks broken"
    )
    assert logged[0][1]["error"] == "missing_scope"
    assert logged[0][1]["needed"] == "chat:write"
