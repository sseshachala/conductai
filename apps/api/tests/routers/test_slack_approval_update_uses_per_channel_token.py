"""Regression: Slack Approve/Reject stopped updating the message after the
per-action-channels refactor (#1142) moved the initial post to
``slack_token_for_channel`` while ``_handle_guard_slack_decision`` kept
using the workspace-default credential. When a workspace's approval
channel had its own ``integration_id`` the update path found no token,
silently skipped ``chat.update``, and the buttons stayed on the card
forever (backend was correctly flipping the row to 'approved').
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
import uuid


# ponytail: opaque tokens so ConductGuard's no-slack-token rule does not
# flag test fixtures. Any distinct string works — we only assert equality.
_WS_DEFAULT_TOK = "TOKEN_workspace_default"
_PER_CHANNEL_TOK = "TOKEN_per_channel_777"


def _fake_payload(channel: str = "C0PERCH", ts: str = "1.000") -> dict:
    return {
        "user": {"name": "sudhi"},
        "container": {"channel_id": channel, "message_ts": ts},
        "actions": [{"action_id": "guard_approve", "value": f"approve:{uuid.uuid4()}"}],
    }


def _prep_common(monkeypatch, ws_uuid, cred_blob):
    from app.routers import webhooks as _wh

    row = SimpleNamespace(
        id=uuid.uuid4(), workspace_id=ws_uuid, status="pending", rule_id="approve-prod-deploy",
    )
    monkeypatch.setattr("app.modules.guard.approval.sweep_if_timed_out", lambda _db, r: r)
    monkeypatch.setattr(
        "app.modules.guard.approval.apply_decision",
        lambda _db, r, **kw: SimpleNamespace(**{**r.__dict__, "status": "approved"}),
    )
    monkeypatch.setattr("app.modules.guard.routers.approvals._resume_workflow_run", MagicMock())
    monkeypatch.setattr("app.core.credentials.get_credential", lambda *a, **kw: cred_blob)

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = row
    return _wh, db, row


def test_update_prefers_per_channel_token_over_workspace_default(monkeypatch):
    ws_uuid = uuid.uuid4()
    _wh, db, _row = _prep_common(
        monkeypatch, ws_uuid,
        {"token": _WS_DEFAULT_TOK},
    )

    per_channel = SimpleNamespace(integration_id="int-777", channel_type="slack", channel_ref="C0PERCH")
    db.query.return_value.filter.return_value.first.return_value = per_channel

    monkeypatch.setattr(
        "app.modules.guard.routers.notifications.slack_token_for_channel",
        lambda _db, _ws, integration_id, default_token: _PER_CHANNEL_TOK if integration_id == "int-777" else default_token,
    )

    seen = {}
    monkeypatch.setattr(
        "app.runtime.integrations.slack.update_approval_message",
        lambda token, channel, ts, status, approver, rule_id=None: seen.update(token=token) or {"ok": True},
    )

    _wh._handle_guard_slack_decision(
        db=db, body=b"", timestamp="0", signature="",
        payload=_fake_payload(),
        request_id_str=str(uuid.uuid4()),
        decision="approved",
        platform_sig_ok=True,
    )
    assert seen.get("token") == _PER_CHANNEL_TOK, (
        f"regression: update used {seen.get('token')!r}. Must resolve per-channel "
        "integration_id first so custom Slack app tokens post the message update."
    )


def test_update_falls_back_to_workspace_default_when_no_channel_row(monkeypatch):
    """Backward compat — pre-refactor workspaces without a
    ``guard_notification_channels`` row still get the message updated
    via the workspace-default token."""
    ws_uuid = uuid.uuid4()
    _wh, db, _row = _prep_common(
        monkeypatch, ws_uuid,
        {"token": _WS_DEFAULT_TOK},
    )
    db.query.return_value.filter.return_value.first.return_value = None

    seen = {}
    monkeypatch.setattr(
        "app.runtime.integrations.slack.update_approval_message",
        lambda token, channel, ts, status, approver, rule_id=None: seen.update(token=token) or {"ok": True},
    )

    _wh._handle_guard_slack_decision(
        db=db, body=b"", timestamp="0", signature="",
        payload=_fake_payload(),
        request_id_str=str(uuid.uuid4()),
        decision="approved",
        platform_sig_ok=True,
    )
    assert seen.get("token") == _WS_DEFAULT_TOK


def test_update_logs_when_token_missing(monkeypatch):
    """Third silent-skip branch: no cred blob at all. Log the reason
    so the next ops person doesn't debug from scratch again."""
    ws_uuid = uuid.uuid4()
    _wh, db, _row = _prep_common(
        monkeypatch, ws_uuid,
        {},  # no token / bot_token AND no signing_secret so platform verify wins
    )
    db.query.return_value.filter.return_value.first.return_value = None

    warns = []
    monkeypatch.setattr(_wh.log, "warning", lambda event, **kw: warns.append((event, kw)))
    monkeypatch.setattr(
        "app.runtime.integrations.slack.update_approval_message",
        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("chat.update must NOT be called without a token")),
    )

    _wh._handle_guard_slack_decision(
        db=db, body=b"", timestamp="0", signature="",
        payload=_fake_payload(),
        request_id_str=str(uuid.uuid4()),
        decision="approved",
        platform_sig_ok=True,
    )
    assert any(ev == "slack.guard_update_skipped_no_token" for ev, _ in warns), (
        "no-token branch must log so silent regressions surface next time"
    )
