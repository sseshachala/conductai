"""Regression test for the Guard-approval Slack button handler in
apps/api/app/routers/webhooks.py::_handle_guard_slack_decision.

Hermetic: no HTTP, no real Slack, no DB. Uses MagicMock for db + row so
the test only asserts the wiring (lookup → apply_decision → resume →
Slack update). Individual primitives are covered by their own tests.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")


def _make_payload(request_id: str, decision_word: str, user: str = "sudhi") -> dict:
    return {
        "user": {"name": user},
        "container": {"channel_id": "C123", "message_ts": "1700000000.001"},
        "actions": [
            {
                "action_id": f"guard_{decision_word}",
                "value": f"{decision_word}:{request_id}",
            }
        ],
    }


def test_guard_approve_flow_wires_apply_decision_and_slack_update():
    from app.routers.webhooks import _handle_guard_slack_decision

    row = SimpleNamespace(
        id="aab035d3-9ce8-4037-a92a-7cfb456da60d",
        workspace_id="ws-1",
        status="pending",
        rule_id="R-42",  # required by update_approval_message payload
    )

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = row

    with patch("app.core.credentials.get_credential", return_value={"token": "xoxb-test"}), \
         patch("app.modules.guard.approval.sweep_if_timed_out", side_effect=lambda db, r: r), \
         patch("app.modules.guard.approval.apply_decision") as mock_apply, \
         patch("app.modules.guard.routers.approvals._resume_workflow_run") as mock_resume, \
         patch("app.runtime.integrations.slack.update_approval_message") as mock_update:

        # apply_decision returns the row with new status
        def _apply(db, r, *, decision, decider_email, decider_user_id, reason):
            r.status = decision
            return r
        mock_apply.side_effect = _apply

        result = _handle_guard_slack_decision(
            db=db,
            body=b'{"noop": true}',
            timestamp="0",
            signature="v0=irrelevant",  # platform-check already passed upstream
            payload=_make_payload("aab035d3-9ce8-4037-a92a-7cfb456da60d", "approve", user="sudhi"),
            request_id_str="aab035d3-9ce8-4037-a92a-7cfb456da60d",
            decision="approved",
            platform_sig_ok=True,
        )

    assert result == {"ok": True}
    assert mock_apply.call_count == 1
    kwargs = mock_apply.call_args.kwargs
    assert kwargs["decision"] == "approved"
    assert kwargs["reason"] == "slack:sudhi"
    assert mock_resume.call_count == 1
    assert mock_update.call_count == 1
    # message stamp uses the freshly-decided status, not the incoming word
    channel, ts, decision, approver = mock_update.call_args.args[1:]
    assert channel == "C123"
    assert ts == "1700000000.001"
    assert decision == "approved"
    assert approver == "sudhi"


def test_guard_unknown_request_is_noop():
    from app.routers.webhooks import _handle_guard_slack_decision

    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = None

    with patch("app.modules.guard.approval.apply_decision") as mock_apply:
        result = _handle_guard_slack_decision(
            db=db,
            body=b'{}',
            timestamp="0",
            signature="v0=x",
            payload=_make_payload("missing", "approve"),
            request_id_str="missing",
            decision="approved",
        )
    assert result == {"ok": True}
    assert mock_apply.call_count == 0


def test_guard_already_decided_row_is_idempotent():
    from app.routers.webhooks import _handle_guard_slack_decision

    row = SimpleNamespace(id="9aab035d-9ce8-4037-a92a-7cfb456da60d", workspace_id="ws-1", status="approved")
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = row

    with patch("app.core.credentials.get_credential", return_value=None), \
         patch("app.modules.guard.approval.sweep_if_timed_out", side_effect=lambda db, r: r), \
         patch("app.modules.guard.approval.apply_decision") as mock_apply, \
         patch("app.modules.guard.routers.approvals._resume_workflow_run") as mock_resume:
        result = _handle_guard_slack_decision(
            db=db,
            body=b'{}',
            timestamp="0",
            signature="v0=x",
            payload=_make_payload("9aab035d-9ce8-4037-a92a-7cfb456da60d", "reject"),
            request_id_str="9aab035d-9ce8-4037-a92a-7cfb456da60d",
            decision="rejected",
        )
    assert result == {"ok": True}
    assert mock_apply.call_count == 0
    assert mock_resume.call_count == 0


def test_guard_workspace_only_signing_secret_path():
    """Platform env var unset — workspace credential's signing_secret is
    used to verify the Slack signature. Proves the fallback works when
    operators only manage secrets in the workspace UI."""
    import hashlib
    import hmac
    import time as _time
    from app.routers.webhooks import _handle_guard_slack_decision

    workspace_secret = "workspace-only-secret"
    body = b'{"noop": true}'
    ts = str(int(_time.time()))
    base = f"v0:{ts}:{body.decode()}"
    good_sig = "v0=" + hmac.new(workspace_secret.encode(), base.encode(), hashlib.sha256).hexdigest()

    row = SimpleNamespace(id="req-ws", workspace_id="ws-1", status="pending")
    db = MagicMock()
    db.query.return_value.filter.return_value.with_for_update.return_value.first.return_value = row

    with patch("app.core.credentials.get_credential",
               return_value={"token": "xoxb-t", "signing_secret": workspace_secret}), \
         patch("app.modules.guard.approval.sweep_if_timed_out", side_effect=lambda db, r: r), \
         patch("app.modules.guard.approval.apply_decision") as mock_apply, \
         patch("app.modules.guard.routers.approvals._resume_workflow_run"), \
         patch("app.runtime.integrations.slack.update_approval_message"):
        def _apply(db, r, *, decision, decider_email, decider_user_id, reason):
            r.status = decision
            return r
        mock_apply.side_effect = _apply

        result = _handle_guard_slack_decision(
            db=db,
            body=body,
            timestamp=ts,
            signature=good_sig,
            payload=_make_payload("aab035d3-9ce8-4037-a92a-7cfb456da60d", "approve", user="sudhi"),
            request_id_str="aab035d3-9ce8-4037-a92a-7cfb456da60d",
            decision="approved",
            platform_sig_ok=False,
        )

    assert result == {"ok": True}
    assert mock_apply.call_count == 1


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-v"]))
