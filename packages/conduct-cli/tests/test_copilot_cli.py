import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

import pytest

from conduct_cli import guard
from conduct_cli.hooks import base, copilot


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "custom-copilot"))
    monkeypatch.setattr("shutil.which", lambda name: "/bin/copilot" if name == "copilot" else None)
    monkeypatch.setattr(guard, "_best_python", lambda: sys.executable)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_fresh_cli_install_gets_mcp_and_hooks_without_vscode(home):
    hook = home / ".conduct" / "hook.py"
    guard._patch_copilot_mcp("test-token", "https://api.example")
    guard._install_copilot_hooks(hook)
    root = guard._copilot_home()
    mcp = json.loads((root / "mcp-config.json").read_text())
    assert mcp["mcpServers"]["conduct-guard"]["headers"]["Authorization"] == "Bearer test-token"
    cfg = json.loads((root / "hooks" / "conduct-guard.json").read_text())
    assert set(cfg["hooks"]) == {"preToolUse", "postToolUse", "postToolUseFailure"}
    assert "test-token" not in json.dumps(cfg)
    assert cfg["hooks"]["preToolUse"][0]["timeoutSec"] > 20
    tool = next(x for x in guard._detect_ai_tools() if x["name"] == "copilot-cli")
    assert tool["hook_registered"] and tool["mcp_registered"]
    assert not tool["proxy_routed"]


def test_sync_preserves_other_mcp_and_hook_files_and_rotates_token(home):
    root = guard._copilot_home()
    (root / "hooks").mkdir(parents=True)
    custom = root / "hooks" / "custom.json"
    custom.write_text('{"version":1,"hooks":{}}')
    mcp = root / "mcp-config.json"
    mcp.write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}, "custom": True}))
    for token in ("old-token", "new-token"):
        guard._patch_copilot_mcp(token, "https://api.example")
        guard._install_copilot_hooks(home / "hook.py")
    cfg = json.loads(mcp.read_text())
    assert cfg["custom"] is True
    assert cfg["mcpServers"]["other"] == {"command": "other"}
    assert "old-token" not in mcp.read_text()
    assert custom.read_text() == '{"version":1,"hooks":{}}'
    assert len(list((root / "hooks").glob("conduct*.json"))) == 1


@pytest.mark.parametrize("tool,expected", [("powershell", "bash"), ("view", "read"), ("create", "write"), ("edit", "edit"), ("mcp__server__tool", "mcp__server__tool")])
def test_payload_normalization(tool, expected):
    result = copilot.normalize({"toolName": tool, "toolArgs": '{"path":"test.txt"}', "sessionId": "session-1"})
    assert result == {"tool_name": expected, "tool_input": {"path": "test.txt", "file_path": "test.txt"}, "session_id": "session-1"}


@pytest.mark.parametrize("code,decision", [(0, None), (2, "deny"), (1, "deny")])
def test_pretool_decision_reuses_shared_engine(code, decision, monkeypatch):
    call = Mock(return_value=subprocess.CompletedProcess([], code, "", ""))
    monkeypatch.setattr(subprocess, "run", call)
    result = copilot.run("pre", Path("hook.py"), {"toolName": "bash", "toolArgs": {"command": "echo hello"}})
    assert result.get("permissionDecision") == decision
    assert call.call_args.args[0][-1] == "conduct_cli.hooks.pretooluse"
    assert call.call_args.kwargs["env"]["CONDUCT_HOOK_SURFACE"] == "copilot-cli"
    assert call.call_args.kwargs["timeout"] == 20


def test_timeout_denies_before_copilot_outer_timeout(monkeypatch):
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=subprocess.TimeoutExpired("guard", 20)))
    result = copilot.run("pre", Path("hook.py"), {"toolName": "bash", "toolArgs": {}})
    assert result["permissionDecision"] == "deny"


@pytest.mark.parametrize("mode,status", [("post", "success"), ("failure", "error")])
def test_post_records_outcome_without_inventing_tokens(mode, status, monkeypatch):
    monkeypatch.setenv("CONDUCT_HOOK_SURFACE", "")
    event = Mock()
    monkeypatch.setattr(base, "post_event", event)
    monkeypatch.setattr(base, "record_hook_heartbeat", Mock())
    result = copilot.run(mode, Path("hook.py"), {"toolName": "bash", "toolArgs": {}, "sessionId": "s1"})
    assert result == {}
    assert event.call_args.kwargs["execution_status"] == status
    assert event.call_args.kwargs["session_id"] == "s1"
    assert not any("token" in k for k in event.call_args.kwargs)
    assert base.detect_ai_tool() == "copilot-cli"


def test_malformed_payload_denies_without_echoing_input(monkeypatch, capsys):
    import io
    monkeypatch.setattr(sys, "argv", ["copilot", "pre", "hook.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO('{"toolName":"bash","toolArgs":"private-malformed"}'))
    copilot.main()
    out = capsys.readouterr().out
    assert json.loads(out)["permissionDecision"] == "deny"
    assert "private-malformed" not in out


@pytest.mark.parametrize("platform,python", [
    ("darwin", "/Applications/Python Tools/python3"),
    ("linux", "/home/user/Python Tools/python3"),
    ("win32", "C:\\Users\\Test User\\Python\\python.exe"),
])
def test_installer_uses_shell_free_executable_on_all_platforms(home, monkeypatch, platform, python):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(guard, "_best_python", lambda: python)
    hook = home / "directory with spaces" / "hook.py"
    guard._install_copilot_hooks(hook)
    cfg = json.loads((guard._copilot_home() / "hooks" / "conduct-guard.json").read_text())
    for entries in cfg["hooks"].values():
        entry = entries[0]
        assert entry["exec"] == python
        assert entry["args"][-1] == str(hook)
        assert "bash" not in entry and "powershell" not in entry


def test_missing_cli_does_not_create_configuration(home, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda _: None)
    guard._install_copilot_hooks(home / "hook.py")
    guard._patch_copilot_mcp("token", "https://api.example")
    assert not guard._copilot_home().exists()


def test_invalid_existing_mcp_config_is_preserved(home):
    root = guard._copilot_home()
    root.mkdir()
    config = root / "mcp-config.json"
    config.write_text("invalid user config")
    guard._patch_copilot_mcp("token", "https://api.example")
    assert config.read_text() == "invalid user config"


def test_native_adapter_entrypoint_without_network():
    result = subprocess.run(
        [sys.executable, "-m", "conduct_cli.hooks.copilot", "pre", "unused.py"],
        input='{"toolName":"bash","toolArgs":[]}', capture_output=True, text=True, check=True,
    )
    assert json.loads(result.stdout)["permissionDecision"] == "deny"


@pytest.mark.parametrize("action,decision", [("block", "deny"), ("warn", None), ("allow", None)])
def test_copilot_rules_use_real_shared_policy_engine(tmp_path, monkeypatch, action, decision):
    import contextlib
    import io
    from conduct_cli.hooks import pretooluse

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"rules": [{"enabled": True, "rule_id": "copilot-shell",
        "match_tool": "bash", "match_ai_tool": "copilot-cli", "match_pattern": "echo",
        "action": action, "message": "test rule"}]}))
    monkeypatch.setattr(pretooluse, "active_policy_path", lambda: policy)
    monkeypatch.setattr(pretooluse, "_verify_policy_signature", lambda _: True)
    monkeypatch.setattr(pretooluse, "_maybe_sync_policy", lambda: None)
    monkeypatch.setattr(pretooluse, "_should_periodic_flush", lambda: False)
    monkeypatch.setattr(pretooluse, "_get_fail_mode", lambda: "fail_closed")
    monkeypatch.setattr(pretooluse, "_get_advisory_mode", lambda: False)
    monkeypatch.setattr(pretooluse, "_load_budget_cache", lambda: (False, None))
    monkeypatch.setattr(pretooluse, "record_hook_heartbeat", Mock())
    monkeypatch.setattr(pretooluse, "_already_warned_this_session", lambda *args: False)
    monkeypatch.setattr(pretooluse, "_record_session_warn", Mock())
    monkeypatch.setattr(base, "hook_receipt_url", lambda _: "https://example.test/receipt")
    events = Mock()
    monkeypatch.setattr(pretooluse, "post_event", events)

    def execute_shared_engine(command, **kwargs):
        monkeypatch.setenv("CONDUCT_HOOK_SURFACE", kwargs["env"]["CONDUCT_HOOK_SURFACE"])
        monkeypatch.setattr(sys, "stdin", io.StringIO(kwargs["input"]))
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            with pytest.raises(SystemExit) as exit_info:
                pretooluse.main()
        return subprocess.CompletedProcess(command, exit_info.value.code, out.getvalue(), err.getvalue())

    monkeypatch.setattr(subprocess, "run", execute_shared_engine)
    result = copilot.run("pre", tmp_path / "hook.py", {"toolName": "powershell",
        "toolArgs": {"command": "echo hello"}, "sessionId": "copilot-session"})
    assert result.get("permissionDecision") == decision
    assert events.call_args.args[3] == "copilot-shell"
    assert events.call_args.args[5] == "copilot-session"
