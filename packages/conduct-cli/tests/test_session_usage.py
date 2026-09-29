import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.hooks import session_usage as usage


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    cfg = {"workspace_id": str(uuid4()), "clerk_user_id": "user", "api_url": "https://api.example"}
    monkeypatch.setattr(usage.base, "load_config", lambda: cfg)
    journal = Mock(return_value=True)
    monkeypatch.setattr(usage.base, "journal_append", journal)
    monkeypatch.setattr(usage.base, "ensure_drain_daemon", Mock())
    path = tmp_path / "transcript.jsonl"
    path.touch()
    data = {"session_id": str(uuid4()), "transcript_path": str(path)}
    return data, path, cfg, journal


def append(path, event):
    with path.open("a") as stream:
        stream.write(json.dumps(event) + "\n")


def codex(tin=100, tout=30):
    return {"type": "event_msg", "payload": {"type": "token_count", "info": {
        "total_token_usage": {"input_tokens": tin, "cached_input_tokens": 50,
                              "output_tokens": tout, "reasoning_output_tokens": 20}}}}


def claude(mid="msg-1", tout=30):
    return {"type": "assistant", "message": {"id": mid, "usage": {
        "input_tokens": 100, "output_tokens": tout, "cache_read_input_tokens": 50,
        "cache_creation_input_tokens": 10}, "content": [{"type": "tool_use", "id": "one"},
                                                        {"type": "tool_use", "id": "two"}]}}


def collect(setup, surface="codex-desktop", expected=None):
    data, _, cfg, _ = setup
    return usage.collect(data, surface, expected or usage.context(cfg))


@pytest.mark.parametrize("surface,event,expected", [
    ("codex-desktop", codex(), (100, 30)), ("claude-code", claude(), (160, 30)),
])
def test_counts_once_without_repeating_cache_reasoning_or_multi_tool_usage(setup, surface, event, expected):
    data, path, _, journal = setup
    assert not collect(setup, surface)
    append(path, event)
    assert collect(setup, surface)
    payload = json.loads(journal.call_args.args[0])
    assert (payload["input_tokens"], payload["output_tokens"]) == expected
    assert payload["hook_session_id"] == data["session_id"]
    assert "content" not in payload and "transcript_path" not in payload
    append(path, event)
    assert not collect(setup, surface)
    assert journal.call_count == 1


@pytest.mark.parametrize("surface", ["codex-cli", "codex-desktop"])
def test_generic_cursor_adopts_specific_surface_without_replaying_usage(setup, surface):
    _, path, _, journal = setup
    append(path, codex())
    collect(setup, "codex")
    assert not collect(setup, surface)
    append(path, codex(110, 35))
    assert collect(setup, "codex")
    payload = json.loads(journal.call_args.args[0])
    assert payload["ai_tool"] == surface
    assert (payload["input_tokens"], payload["output_tokens"]) == (10, 5)
    assert not collect(setup, surface)
    assert journal.call_count == 1


@pytest.mark.parametrize("detected,expected", [
    ("codex-cli", "codex-cli"), ("codex-desktop", "codex-desktop"),
    ("claude-code", "codex"), ("cursor", "codex"),
])
def test_generic_lifecycle_resolves_codex_surface_before_spawning(setup, monkeypatch, detected, expected):
    data, _, _, _ = setup
    collector = Mock()
    spawn = Mock()
    monkeypatch.setattr(usage.base, "detect_ai_tool", lambda: detected)
    monkeypatch.setattr(usage, "collect", collector)
    monkeypatch.setattr(usage.subprocess, "Popen", spawn)
    usage.handle(data, "codex", poll=True)
    assert collector.call_args.args[1] == expected
    assert spawn.call_args.args[0][4] == expected


def test_cli_signal_takes_precedence_over_desktop_path(monkeypatch):
    for key in ("CONDUCT_HOOK_SURFACE", "CLAUDE_CODE_ENTRYPOINT", "CLAUDECODE",
                "CLAUDE_DESKTOP_ENTRYPOINT", "CLAUDE_DESKTOP", "CODEX_CLI_VERSION"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CODEX_SESSION_ID", str(uuid4()))
    monkeypatch.setenv("PATH", "/Applications/Codex.app/Contents/MacOS:/usr/bin")
    assert usage.base.detect_ai_tool() == "codex-cli"


def test_codex_lifecycle_and_desktop_share_cursor(setup):
    _, path, _, journal = setup
    collect(setup, "codex")
    append(path, codex())
    assert collect(setup, "codex-desktop")
    assert not collect(setup, "codex-cli")
    assert journal.call_count == 1


def test_claude_streaming_extensions_only_add_delta(setup):
    _, path, _, journal = setup
    collect(setup, "claude-code")
    append(path, claude(tout=10))
    collect(setup, "claude-code")
    append(path, claude(tout=30))
    collect(setup, "claude-code")
    payload = json.loads(journal.call_args.args[0])
    assert (payload["input_tokens"], payload["output_tokens"]) == (0, 20)


@pytest.mark.parametrize("surface,event", [("codex-desktop", codex()), ("claude-code", claude())])
def test_initial_scan_does_not_import_history(setup, surface, event):
    _, path, _, journal = setup
    append(path, event)
    assert not collect(setup, surface)
    journal.assert_not_called()


def test_large_tool_output_cannot_hide_claude_usage(setup):
    _, path, _, journal = setup
    collect(setup, "claude-code")
    append(path, claude())
    append(path, {"type": "user", "message": "private-output" * 10000})
    assert collect(setup, "claude-code")
    assert "private-output" not in journal.call_args.args[0]


def test_partial_last_record_is_retried(setup):
    _, path, _, journal = setup
    collect(setup)
    record = json.dumps(codex())
    path.write_text(record[:50])
    assert not collect(setup)
    with path.open("a") as stream:
        stream.write(record[50:] + "\n")
    assert collect(setup)
    assert journal.call_count == 1


def test_journal_failure_does_not_advance_cursor_and_retry_id_is_stable(setup):
    _, path, _, journal = setup
    collect(setup)
    append(path, codex())
    journal.return_value = False
    assert not collect(setup)
    first = json.loads(journal.call_args.args[0])
    journal.return_value = True
    assert collect(setup)
    second = json.loads(journal.call_args.args[0])
    assert first["snapshot_id"] == second["snapshot_id"]
    assert second["input_tokens"] == 100


def test_workspace_switch_does_not_upload_old_context(setup):
    _, path, cfg, journal = setup
    expected = usage.context(cfg)
    collect(setup)
    append(path, codex())
    cfg["workspace_id"] = str(uuid4())
    assert not collect(setup, expected=expected)
    assert not collect(setup)
    journal.assert_not_called()
    append(path, codex(200, 60))
    collect(setup)
    cfg["workspace_id"] = expected[1]
    assert not collect(setup)
    append(path, codex(210, 62))
    collect(setup)
    payload = json.loads(journal.call_args.args[0])
    assert (payload["input_tokens"], payload["output_tokens"]) == (10, 2)


def test_reset_rebaselines_without_counting_gap(setup):
    _, path, _, journal = setup
    append(path, codex())
    collect(setup)
    append(path, codex(1, 1))
    assert not collect(setup)
    append(path, codex(11, 3))
    assert collect(setup)
    payload = json.loads(journal.call_args.args[0])
    assert (payload["input_tokens"], payload["output_tokens"]) == (10, 2)


def test_identical_deltas_after_reset_have_distinct_snapshot_ids(setup):
    _, path, _, journal = setup
    collect(setup)
    append(path, codex())
    collect(setup)
    first = json.loads(journal.call_args.args[0])["snapshot_id"]
    append(path, codex(0, 0))
    assert not collect(setup)
    append(path, codex())
    assert collect(setup)
    assert json.loads(journal.call_args.args[0])["snapshot_id"] != first


@pytest.mark.parametrize("surface,relative", [("codex", ".codex/sessions/2026/09/28/rollout-date-{sid}.jsonl"),
                                             ("claude-code", ".claude/projects/project/{sid}.jsonl")])
def test_missing_path_resolves_only_exact_session(setup, surface, relative):
    data, _, _, _ = setup
    target = Path.home() / relative.format(sid=data["session_id"])
    target.parent.mkdir(parents=True)
    target.touch()
    assert usage.transcript({"session_id": data["session_id"]}, surface) == target.resolve()
    assert usage.transcript({"session_id": str(uuid4())}, surface) is None


@pytest.mark.parametrize("value", [-1, True, 1.2, None])
def test_invalid_usage_not_uploaded(setup, value):
    _, path, _, journal = setup
    collect(setup)
    append(path, codex(value))
    assert not collect(setup)
    journal.assert_not_called()
    append(path, codex())
    assert collect(setup)


def test_detached_worker_does_not_receive_credentials_or_tool_input(setup, monkeypatch):
    data, _, cfg, _ = setup
    cfg["agent_token"] = "private-token"
    data["tool_input"] = {"command": "private-command"}
    spawn = Mock()
    monkeypatch.setattr(usage.subprocess, "Popen", spawn)
    usage.handle(data, "codex", poll=True)
    assert "private-token" not in str(spawn.call_args)
    assert "private-command" not in str(spawn.call_args)
    assert spawn.call_args.kwargs.get("start_new_session") or spawn.call_args.kwargs.get("creationflags")


@pytest.mark.parametrize("platform", ["darwin", "linux", "win32"])
def test_lifecycle_hooks_preserve_user_hooks_and_are_idempotent(monkeypatch, platform):
    from conduct_cli.guard_commands import hooks
    monkeypatch.setattr(hooks.sys, "platform", platform)
    monkeypatch.setattr(hooks, "_best_python", lambda: "C:/Python Tools/python.exe" if platform == "win32" else "/Python Tools/python3")
    user_hook = {"hooks": [{"type": "command", "command": "user-command"}]}
    config = {"Stop": [user_hook]}
    assert hooks._usage_lifecycle_hooks(config, "codex")
    assert not hooks._usage_lifecycle_hooks(config, "codex")
    assert config["Stop"][0] == user_hook
    assert all(len(config[event]) == (2 if event == "Stop" else 1) for event in ("SessionStart", "Stop", "SessionEnd"))
    command = config["SessionStart"][0]["hooks"][0]["command"]
    assert command.startswith('"C:/Python Tools/python.exe"') if platform == "win32" else command.startswith("'/Python Tools/python3'")


@pytest.mark.parametrize("surface", ["codex-desktop", "claude-code"])
def test_post_hook_keeps_model_tokens_off_tool_rows(setup, monkeypatch, surface):
    import io
    from conduct_cli.hooks import posttooluse
    data, _, _, _ = setup
    data.update(tool_name="Bash", tool_use_id="non-prefixed-id", tool_input={}, tool_response="ok")
    monkeypatch.setattr(posttooluse.sys, "stdin", io.StringIO(json.dumps(data)))
    monkeypatch.setattr(posttooluse, "detect_ai_tool", lambda: surface)
    monkeypatch.setattr(posttooluse, "record_hook_heartbeat", Mock())
    monkeypatch.setattr(posttooluse, "_compute_blast_radius", Mock(return_value=None))
    monkeypatch.setattr(posttooluse, "check_policy", Mock(return_value=(None, "allow", None, None)))
    report = Mock()
    collect_usage = Mock()
    monkeypatch.setattr(posttooluse, "_post_usage", report)
    monkeypatch.setattr(usage, "handle", collect_usage)
    with pytest.raises(SystemExit):
        posttooluse.main()
    assert report.call_args.args[2:4] == (None, None)
    assert report.call_args.args[-1] == "non-prefixed-id"
    assert collect_usage.call_args.kwargs["poll"] is True


def test_oversized_tool_line_and_partial_line_recovery(setup, monkeypatch):
    _, path, _, journal = setup
    collect(setup)
    monkeypatch.setattr(usage, "MAX_LINE", 512)
    path.write_text(json.dumps({"type": "tool-output", "text": "private" * 1000}))
    assert not collect(setup)
    with path.open("a") as stream:
        stream.write("\n")
    append(path, codex())
    assert collect(setup)
    assert json.loads(journal.call_args.args[0])["input_tokens"] == 100
