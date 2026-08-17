"""Tests for `conduct guard approvals list|approve|reject` CLI (#1140).

Mocks _req + _require_guard_config so no network. Verifies URL/body shape
for decide, output for list (populated + empty), and dispatcher routing.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve()
CLI_PKG = HERE.parent.parent / "src"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))

_FAKE_CFG = {
    "workspace_id": "ws-abc-123",
    "agent_token":  "cond_agt_test",
    "api_url":      "https://api.example.com",
}


@pytest.fixture(autouse=True)
def patch_config(monkeypatch):
    import conduct_cli.guard as g
    monkeypatch.setattr(g, "_require_guard_config", lambda: _FAKE_CFG)
    monkeypatch.setattr(g, "_api_url", lambda cfg: cfg["api_url"])


def _parse(*argv):
    import conduct_cli.guard as g
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="command")
    guard_p, _ = g.register_guard_parser(s)
    return p.parse_args(list(argv)), guard_p


def test_parser_routes_list_approve_reject():
    args, _ = _parse("guard", "approvals", "list", "--status", "approved", "--limit", "5")
    assert args.approvals_command == "list"
    assert args.status == "approved" and args.limit == 5

    args, _ = _parse("guard", "approvals", "approve", "req-1", "--reason", "ok")
    assert args.approvals_command == "approve" and args.request_id == "req-1" and args.reason == "ok"

    args, _ = _parse("guard", "approvals", "reject", "req-2")
    assert args.approvals_command == "reject" and args.reason is None


def test_list_renders_rows(capsys):
    import conduct_cli.guard as g
    resp = {"items": [
        {"id":"req-1","requester_email":"a@x.io","rule_id":"r.one","rule_message":"m1","status":"pending"},
        {"id":"req-2","requester_email":"b@x.io","rule_id":"r.two","rule_message":"m2","status":"approved"},
    ]}
    args, guard_p = _parse("guard", "approvals", "list")
    with patch.object(g, "_req", return_value=resp) as mock:
        g.dispatch_guard(args, guard_p)
    call_url = mock.call_args.args[1]
    assert "/guard/approvals" in call_url and "status=pending" in call_url and "workspace_id=ws-abc-123" in call_url
    out = capsys.readouterr().out
    assert "req-1" in out and "req-2" in out
    assert "pending" in out and "approved" in out


def test_list_empty_state(capsys):
    import conduct_cli.guard as g
    args, guard_p = _parse("guard", "approvals", "list", "--status", "all")
    with patch.object(g, "_req", return_value={"items": []}):
        g.dispatch_guard(args, guard_p)
    out = capsys.readouterr().out
    assert "No approvals" in out


def test_approve_sends_correct_body_and_url(capsys):
    import conduct_cli.guard as g
    decision_resp = {
        "request": {"rule_id":"r.x","decided_by_email":"me@x.io","latency_ms":42,"status":"approved"},
        "run_resumed": True,
    }
    args, guard_p = _parse("guard", "approvals", "approve", "req-9", "--reason", "looks ok")
    with patch.object(g, "_req", return_value=decision_resp) as mock:
        g.dispatch_guard(args, guard_p)
    method, url = mock.call_args.args[0], mock.call_args.args[1]
    body = mock.call_args.kwargs["body"]
    assert method == "POST"
    assert "/guard/approvals/req-9/decide" in url and "workspace_id=ws-abc-123" in url
    assert body == {"decision": "approved", "reason": "looks ok"}
    out = capsys.readouterr().out
    assert "APPROVED" in out and "run_resumed=True" in out and "42ms" in out


def test_reject_without_reason_omits_field(capsys):
    import conduct_cli.guard as g
    decision_resp = {
        "request": {"rule_id":"r.x","decided_by_email":"me@x.io","latency_ms":10,"status":"rejected"},
        "run_resumed": False,
    }
    args, guard_p = _parse("guard", "approvals", "reject", "req-9")
    with patch.object(g, "_req", return_value=decision_resp) as mock:
        g.dispatch_guard(args, guard_p)
    body = mock.call_args.kwargs["body"]
    assert body == {"decision": "rejected"}  # no reason key when None
    out = capsys.readouterr().out
    assert "REJECTED" in out


def test_bare_approvals_prints_help(capsys):
    import conduct_cli.guard as g
    args, guard_p = _parse("guard", "approvals")
    with pytest.raises(SystemExit) as excinfo:
        g.dispatch_guard(args, guard_p)
    assert excinfo.value.code == 1
