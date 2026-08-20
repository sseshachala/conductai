"""E2E tests for the hook-layer approval gate.

Fills the coverage gap identified in the approval-surface audit: unit tests
verify check_policy returns action='approval', but nothing exercised the full
"rule fires → approval request created → approver decides → agent
unblocks/blocks" flow at the hook layer.

Covers:
  1. _guard_approval_request → returns "approved" when server reports approved
  2. _guard_approval_request → returns "rejected" when server reports rejected
  3. _guard_approval_request → returns "timed_out" when polling deadline passes
  4. _guard_approval_request → returns "unavailable" when config is missing
  5. main() → full pipeline: approval rule fires, mock approver approves,
     hook exits 0 with post_event(allowed, [approval:approved])
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

CONDUCT_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CONDUCT_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CONDUCT_CLI_SRC))

import conduct_cli.hooks.pretooluse as pt


# ── fake urlopen helpers ──────────────────────────────────────────────────────

def _mk_response(payload: dict):
    """Return a context-manager-shaped fake urlopen response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda self, *a: False
    return resp


def _fake_urlopen(create_payload, poll_sequence):
    """Return a fake urlopen callable.

    First call returns create_payload (the POST /guard/approvals response).
    Subsequent calls cycle through poll_sequence (GET /guard/approvals/{id}).
    """
    calls = {"n": 0}
    def _side_effect(req, timeout=None):
        n = calls["n"]
        calls["n"] += 1
        if n == 0:
            return _mk_response(create_payload)
        idx = min(n - 1, len(poll_sequence) - 1)
        return _mk_response(poll_sequence[idx])
    return _side_effect


@pytest.fixture()
def config(monkeypatch):
    monkeypatch.setattr(pt, "load_config", lambda: {
        "workspace_id": "ws-test",
        "agent_token":  "cond_agt_test",
        "api_url":      "https://api.example.test",
    })


# ── _guard_approval_request outcomes ─────────────────────────────────────────

class TestApprovalRequestOutcomes:
    def test_approved(self, config, monkeypatch):
        monkeypatch.setattr(pt, "time", MagicMock(time=lambda: 0.0, sleep=lambda _s: None))
        urlopen = _fake_urlopen(
            create_payload={"id": "req-1", "url": "https://ui/req-1"},
            poll_sequence=[{"status": "pending"}, {"status": "approved"}],
        )
        with patch("urllib.request.urlopen", side_effect=urlopen):
            outcome = pt._guard_approval_request("bash", {"command": "rm -rf /"}, "test-rule", "risky", "s-1")
        assert outcome == "approved"

    def test_rejected(self, config, monkeypatch):
        monkeypatch.setattr(pt, "time", MagicMock(time=lambda: 0.0, sleep=lambda _s: None))
        urlopen = _fake_urlopen(
            create_payload={"id": "req-2", "url": "https://ui/req-2"},
            poll_sequence=[{"status": "rejected"}],
        )
        with patch("urllib.request.urlopen", side_effect=urlopen):
            outcome = pt._guard_approval_request("bash", {"command": "rm -rf /"}, "test-rule", "risky", "s-1")
        assert outcome == "rejected"

    def test_timed_out(self, config, monkeypatch):
        # advance clock past the 300s deadline on the second call
        clock = {"t": 0.0}
        def _now():
            clock["t"] += 400.0
            return clock["t"]
        monkeypatch.setattr(pt, "time", MagicMock(time=_now, sleep=lambda _s: None))
        urlopen = _fake_urlopen(
            create_payload={"id": "req-3", "url": "https://ui/req-3"},
            poll_sequence=[{"status": "pending"}],
        )
        with patch("urllib.request.urlopen", side_effect=urlopen):
            outcome = pt._guard_approval_request("bash", {"command": "rm -rf /"}, "test-rule", "risky", "s-1")
        assert outcome == "timed_out"

    def test_unavailable_missing_config(self, monkeypatch):
        monkeypatch.setattr(pt, "load_config", lambda: {"api_url": "https://api.example.test"})
        outcome = pt._guard_approval_request("bash", {"command": "rm -rf /"}, "test-rule", "risky", "s-1")
        assert outcome == "unavailable"

    def test_unavailable_on_network_error(self, config, monkeypatch):
        monkeypatch.setattr(pt, "time", MagicMock(time=lambda: 0.0, sleep=lambda _s: None))
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            outcome = pt._guard_approval_request("bash", {"command": "rm -rf /"}, "test-rule", "risky", "s-1")
        assert outcome == "unavailable"


# ── full-pipeline: main() approval flow ──────────────────────────────────────

class TestMainApprovalPipeline:
    def test_approved_exits_zero_and_posts_allowed(self, tmp_path, config, monkeypatch, capsys):
        # policy with an approval rule that matches "rm -rf"
        pol = tmp_path / "policy.json"
        pol.write_text(json.dumps({"version": "test", "rules": [{
            "rule_id":       "danger-rm",
            "match_tool":    "shell",
            "match_pattern": r"\brm\s+-rf\b",
            "action":        "approval",
            "message":       "rm -rf needs human approval",
        }]}))
        monkeypatch.setattr(pt, "active_policy_path", lambda: pol)
        monkeypatch.setattr(pt, "_verify_policy_signature", lambda _: True)
        monkeypatch.setattr(pt, "_get_advisory_mode", lambda: False)
        monkeypatch.setattr(pt, "_maybe_sync_policy", lambda: None)
        monkeypatch.setattr(pt, "_should_periodic_flush", lambda: False)
        monkeypatch.setattr(pt, "time", MagicMock(time=lambda: 0.0, sleep=lambda _s: None))

        # capture post_event to assert the emitted decision
        events = []
        monkeypatch.setattr(pt, "post_event", lambda *a, **kw: events.append((a, kw)))

        # simulate Claude Code hook input on stdin
        stdin_payload = {
            "session_id": "sess-e2e",
            "tool_name":  "Bash",
            "tool_input": {"command": "rm -rf /tmp/xxx"},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stdin_payload)))

        # approver approves on first poll
        urlopen = _fake_urlopen(
            create_payload={"id": "req-e2e", "url": "https://ui/req-e2e"},
            poll_sequence=[{"status": "approved"}],
        )

        with patch("urllib.request.urlopen", side_effect=urlopen):
            with pytest.raises(SystemExit) as exc:
                pt.main()

        assert exc.value.code == 0, "approved outcome must exit 0"
        assert events, "post_event must have been called"
        # first positional arg is tool_name, third is decision string
        args, _ = events[-1]
        decision = args[2]
        rule_id  = args[3]
        message  = args[4]
        assert decision == "allowed"
        assert rule_id == "danger-rm"
        assert "[approval:approved]" in message
