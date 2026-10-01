import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conduct_cli.guard_commands import editor_setup
from conduct_cli.hooks import editors, base


@pytest.mark.parametrize("surface,payload,tool", [
    ("cursor", {"tool_name": "Shell", "tool_input": {"command": "echo test"}, "conversation_id": "session"}, "bash"),
    ("windsurf", {"agent_action_name": "pre_run_command", "tool_info": {"command_line": "echo test"}}, "bash"),
    ("windsurf", {"agent_action_name": "pre_mcp_tool_use", "tool_info": {"mcp_tool_name": "lookup", "mcp_tool_arguments": {}}}, "lookup"),
])
def test_payload_contract(surface, payload, tool):
    normalized = editors.normalize(surface, payload)
    assert normalized["tool_name"] == tool
    assert set(normalized) == {"tool_name", "tool_input", "session_id"}


@pytest.mark.parametrize("surface", ["cursor", "windsurf"])
def test_install_is_idempotent_and_remove_preserves_other_hooks(surface, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = editor_setup.ADAPTERS[surface].root()
    root.mkdir(parents=True)
    event = next(iter(editor_setup.EVENTS[surface]))
    original = {"hooks": {event: [{"command": "user-hook"}]}, "other": True}
    path = root / "hooks.json"
    path.write_text(json.dumps(original))
    assert editor_setup.configure(surface, "/private/python path/python")
    assert not editor_setup.configure(surface, "/private/python path/python")
    data = json.loads(path.read_text())
    assert data["hooks"][event][0] == {"command": "user-hook"}
    if surface == "cursor":
        assert data["hooks"][event][1]["failClosed"] is True
    assert editor_setup.configure(surface, "/another/python", remove=True)
    final = json.loads(path.read_text())
    assert final["hooks"] == original["hooks"]
    assert final["other"]


def test_invalid_config_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    root = editor_setup.ADAPTERS["cursor"].root()
    root.mkdir()
    path = root / "hooks.json"
    path.write_text("invalid-json")
    with pytest.raises(ValueError):
        editor_setup.configure("cursor", "python")
    assert path.read_text() == "invalid-json"


@pytest.mark.parametrize("failure", [2, 1, "timeout"])
def test_pre_hook_denies_failures_without_echoing_output(failure, tmp_path, monkeypatch):
    monkeypatch.setattr(base, "load_config", lambda: {"workspace_id": "test"})
    monkeypatch.setattr(base, "active_policy_path", lambda: tmp_path)
    if failure == "timeout":
        effect = editors.subprocess.TimeoutExpired("python", 20)
        mock = Mock(side_effect=effect)
    else:
        mock = Mock(return_value=SimpleNamespace(returncode=failure, stdout="private", stderr="private"))
    monkeypatch.setattr(editors.subprocess, "run", mock)
    assert editors.run("cursor", "pre", {"tool_name": "Shell", "tool_input": {"command": "test"}}) is False
    assert mock.call_args.kwargs["timeout"] == 20
    assert mock.call_args.kwargs["env"]["CONDUCT_HOOK_SURFACE"] == "cursor"


def test_missing_policy_denies_without_starting_child(tmp_path, monkeypatch):
    monkeypatch.setattr(base, "load_config", lambda: {"workspace_id": "test"})
    monkeypatch.setattr(base, "active_policy_path", lambda: tmp_path / "absent")
    monkeypatch.setattr(editors.subprocess, "run", lambda *a, **kw: pytest.fail("Started child"))
    assert not editors.run("cursor", "pre", {"tool_name": "Read", "tool_input": {}})


def test_post_hook_does_not_upload_tool_results(monkeypatch):
    post = Mock()
    monkeypatch.setattr(base, "post_event", post)
    monkeypatch.setattr(base, "record_hook_heartbeat", lambda _: None)
    monkeypatch.setenv("CONDUCT_HOOK_SURFACE", "windsurf")
    assert editors.run("windsurf", "post", {"agent_action_name": "post_mcp_tool_use",
        "tool_info": {"mcp_tool_name": "lookup", "mcp_tool_arguments": {}, "mcp_result": "SENSITIVE_TOOL_RESULT"}})
    assert "SENSITIVE_TOOL_RESULT" not in str(post.call_args)
    assert base.detect_ai_tool() == "windsurf"
