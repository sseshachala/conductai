"""Tests for conduct_cli.hooks.pretooluse.check_policy.

Regression coverage for a bug that shipped in commit c7b7113: the entry point
lowercased tool_name to "bash" but check_policy compared against literal
"Bash", so the shell-command extraction branch was unreachable. Every Bash
tool call matched patterns against json.dumps(tool_input) instead of the raw
command, silently disabling all ^-anchored shell rules.

Fix: match tool_name against expand_match_tool("shell") and use
_bash_scan_target so ^-anchored rules and rules that inspect argv beyond
argv[1] work as authored.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

CONDUCT_CLI_SRC = Path(__file__).resolve().parent.parent / "src"
if str(CONDUCT_CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CONDUCT_CLI_SRC))

import conduct_cli.hooks.pretooluse as pt
from conduct_cli.hooks.pretooluse import check_policy


def _rule(**kw):
    r = {
        "rule_id": kw.pop("rule_id", "test-rule"),
        "match_tool": kw.pop("match_tool", "shell"),
        "match_pattern": kw.pop("match_pattern", None),
        "action": kw.pop("action", "block"),
        "message": kw.pop("message", "Test violation"),
    }
    r.update(kw)
    return r


@pytest.fixture()
def policy(tmp_path, monkeypatch):
    """Write a policy file and patch active_policy_path + signature check."""
    def _make(rules):
        p = tmp_path / "policy.json"
        p.write_text(json.dumps({"version": "test", "rules": rules}))
        monkeypatch.setattr(pt, "active_policy_path", lambda: p)
        monkeypatch.setattr(pt, "_verify_policy_signature", lambda _: True)
        return p
    return _make


# ── regression: anchor-based rules must fire against raw command ─────────────

class TestAnchoredShellRules:
    def test_caret_anchor_matches_raw_command(self, policy):
        # Bug: ^\s*boot\s+system\b never matched because pattern was tested
        # against json.dumps({"command": "boot system primary"}) which starts
        # with `{`. Fix: pattern is tested against the raw command string.
        policy([_rule(
            rule_id="anchor-boot",
            match_pattern=r"^\s*boot\s+system\b",
        )])
        _, action, rule_id, _ = check_policy("bash", {"command": "boot system primary"})
        assert action == "block"
        assert rule_id == "anchor-boot"

    def test_argv_beyond_signature_matches(self, policy):
        # Bug: _bash_operator_signature dropped argv[2+], so a rule requiring
        # "boot system primary" (three tokens) could not match. Fix: matcher
        # uses _bash_scan_target which preserves the full command.
        policy([_rule(
            rule_id="firmware-downgrade",
            match_pattern=r"\bboot\s+system\s+(?:primary|secondary|flash)\b",
        )])
        _, action, rule_id, _ = check_policy("bash", {"command": "boot system primary"})
        assert action == "block"
        assert rule_id == "firmware-downgrade"

    def test_no_false_match_on_unrelated_command(self, policy):
        policy([_rule(
            rule_id="anchor-boot",
            match_pattern=r"^\s*boot\s+system\b",
        )])
        _, action, _, _ = check_policy("bash", {"command": "ls -la /var/log"})
        assert action == "allow"


# ── tool_name normalization: shell aliases all extract command ───────────────

class TestShellAliasExtraction:
    @pytest.mark.parametrize("tool_name", ["bash", "shell", "terminal", "run_command", "execute"])
    def test_shell_alias_matches_raw_command(self, policy, tool_name):
        policy([_rule(
            rule_id="anchor-boot",
            match_pattern=r"^\s*boot\s+system\b",
        )])
        _, action, rule_id, _ = check_policy(tool_name, {"command": "boot system primary"})
        assert action == "block", f"tool_name={tool_name} should use raw command extraction"
        assert rule_id == "anchor-boot"

    def test_non_shell_tool_uses_json_blob(self, policy):
        # write_file is not a shell alias — falls to the else branch which
        # tests against json.dumps(tool_input). The command-key is present
        # but should not be extracted as a shell command.
        policy([_rule(
            rule_id="anchor-boot",
            match_tool="filesystem-write",
            match_pattern=r"^\s*boot\s+system\b",
        )])
        _, action, _, _ = check_policy("write", {"file_path": "/tmp/x", "content": "boot system primary"})
        # anchor won't match json blob starting with `{`, so no block
        assert action == "allow"
