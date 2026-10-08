"""Team-memory capture/injection per surface (#2389): extractors, labels, hook wiring."""
import io
import json
import sys
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli import memory, transcript_text
from conduct_cli.hooks import copilot, pretooluse, session_usage

# Non-ASCII on purpose: Windows' default cp1252 codec cannot round-trip these.
CLAUDE = [
    {"type": "user", "message": {"role": "user", "content": "Fix the café ✓ login bug"}},
    {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "thinking", "thinking": "private"},
        {"type": "text", "text": "Root cause: JWT clock skew → added 30s leeway."},
        {"type": "tool_use", "name": "Edit", "input": {"file_path": "auth.py"}}]}},
    {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
]
CODEX = [
    {"type": "session_meta", "payload": {"id": "x", "cwd": "/repo"}},
    {"type": "response_item", "payload": {"type": "message", "role": "developer",
                                          "content": [{"type": "input_text", "text": "sandbox rules"}]}},
    {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [
        {"type": "input_text", "text": "<environment_context>cwd</environment_context>"},
        {"type": "input_text", "text": "Why does the naïve retry loop spin?"}]}},
    {"type": "response_item", "payload": {"type": "reasoning", "content": [{"type": "text", "text": "hmm"}]}},
    {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command", "arguments": "{}"}},
    {"type": "response_item", "payload": {"type": "message", "role": "assistant", "content": [
        {"type": "output_text", "text": "Backoff was never applied — fixed in retry.py ✓"}]}},
    {"type": "event_msg", "payload": {"type": "token_count", "info": {}}},
]
COPILOT = [
    {"type": "session.start", "data": {}},
    {"type": "user.message", "data": {"content": "Add Résumé upload validation"}},
    {"type": "tool.execution_start", "data": {"toolName": "bash"}},
    {"type": "assistant.message", "data": {"content": "Validated MIME type → rejects .exe", "toolRequests": []}},
    {"type": "system.message", "data": {"content": "system prompt"}},
]


def write_jsonl(path: Path, records) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records) + "{partial",
                    encoding="utf-8")
    return path


def test_claude_extractor(tmp_path):
    out = transcript_text.EXTRACTORS["claude-jsonl"](write_jsonl(tmp_path / "c.jsonl", CLAUDE))
    assert out == ["user: Fix the café ✓ login bug", "assistant: Root cause: JWT clock skew → added 30s leeway."]


def test_codex_extractor_keeps_only_conversation(tmp_path):
    out = transcript_text.EXTRACTORS["codex-jsonl"](write_jsonl(tmp_path / "x.jsonl", CODEX))
    assert out == ["user: Why does the naïve retry loop spin?",
                   "assistant: Backoff was never applied — fixed in retry.py ✓"]


def test_copilot_extractor(tmp_path):
    out = transcript_text.EXTRACTORS["copilot-jsonl"](write_jsonl(tmp_path / "events.jsonl", COPILOT))
    assert out == ["user: Add Résumé upload validation", "assistant: Validated MIME type → rejects .exe"]


def test_claude_parser_finds_nothing_in_codex_transcript(tmp_path):
    """The old bug: Codex logs parsed as Claude JSONL yield garbage/empty text."""
    assert transcript_text.EXTRACTORS["claude-jsonl"](write_jsonl(tmp_path / "x.jsonl", CODEX)) == []


def test_tail_read_skips_partial_first_line(tmp_path, monkeypatch):
    path = write_jsonl(tmp_path / "c.jsonl", CLAUDE * 50)
    monkeypatch.setattr(transcript_text, "TAIL_BYTES", 400)
    out = transcript_text.EXTRACTORS["claude-jsonl"](path)
    assert out and len(out) < 100


@pytest.mark.parametrize("surface,fmt", [
    ("claude-code", "claude-jsonl"), ("codex-cli", "codex-jsonl"), ("codex-desktop", "codex-jsonl"),
    ("codex", "codex-jsonl"), ("copilot-cli", "copilot-jsonl"),
    ("cursor", None), ("windsurf", None), ("claude-desktop", None), ("", None), (None, None),
])
def test_transcript_format_by_surface(surface, fmt):
    assert transcript_text.transcript_format(surface) == fmt


def test_copilot_transcript_resolved_from_session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    session = str(uuid4())
    write_jsonl(tmp_path / "session-state" / session / "events.jsonl", COPILOT)
    text = transcript_text.learnings_text("copilot-jsonl", session, None)
    assert "Résumé" in text and "rejects .exe" in text
    assert transcript_text.learnings_text("copilot-jsonl", "../../etc", None) is None


@pytest.fixture
def posted(monkeypatch):
    sent = []
    monkeypatch.setattr(memory, "_load_config", lambda: {
        "server": "https://api.example", "agent_token": "t", "workspace_id": "ws", "user_id": "u1"})

    def urlopen(req, timeout=None):
        sent.append(json.loads(req.data))
    monkeypatch.setattr(memory.urllib.request, "urlopen", urlopen)
    return sent


def test_codex_transcript_is_never_posted_as_claude_code(tmp_path, posted, monkeypatch):
    path = write_jsonl(tmp_path / "rollout.jsonl", CODEX)
    # No explicit tool: the label comes from surface detection, not a hardcode.
    monkeypatch.setattr("conduct_cli.hooks.base.detect_ai_tool", lambda: "codex-cli")
    assert memory.post_session_to_api(str(uuid4()), str(path), "acme/repo", wait=True)
    assert posted[0]["tool"] == "codex-cli"
    assert posted[0]["repo_full_name"] == "acme/repo"
    assert "naïve retry" in posted[0]["raw_transcript"]
    assert all(p["tool"] != "claude_code" for p in posted)


def test_claude_post_uses_surface_label(tmp_path, posted):
    path = write_jsonl(tmp_path / "c.jsonl", CLAUDE)
    assert memory.post_session_to_api(str(uuid4()), str(path), None, tool="claude-code", wait=True)
    assert posted[0]["tool"] == "claude-code"  # API normalises to the legacy claude_code label


def test_unknown_surface_posts_nothing(tmp_path, posted):
    path = write_jsonl(tmp_path / "c.jsonl", CLAUDE)
    assert not memory.post_session_to_api(str(uuid4()), str(path), None, tool="cursor", wait=True)
    assert posted == []


def test_periodic_flush_gated_on_known_format(tmp_path, posted, monkeypatch):
    monkeypatch.setattr(pretooluse, "_mark_flushed", Mock())
    monkeypatch.setattr(pretooluse, "detect_repo", lambda: None)
    path = write_jsonl(tmp_path / "rollout.jsonl", CODEX)
    monkeypatch.setattr(pretooluse, "detect_ai_tool", lambda: "cursor")
    pretooluse._flush_team_memory({"session_id": str(uuid4()), "transcript_path": str(path)})
    pretooluse._mark_flushed.assert_not_called()
    monkeypatch.setattr(pretooluse, "detect_ai_tool", lambda: "codex-cli")
    monkeypatch.setattr(memory.threading, "Thread", lambda target, daemon: Mock(start=target))
    pretooluse._flush_team_memory({"session_id": str(uuid4()), "transcript_path": str(path)})
    assert [p["tool"] for p in posted] == ["codex-cli"]


def test_spawn_capture_is_detached_and_skips_unknown(monkeypatch):
    spawn = Mock()
    monkeypatch.setattr("conduct_cli.hooks.base.spawn_detached", spawn)
    memory.spawn_capture("cursor", "s", None)
    spawn.assert_not_called()
    memory.spawn_capture("codex-cli", "s", "/t.jsonl")
    assert spawn.call_args.args[0][1:] == ["-m", "conduct_cli.memory", "capture", "codex-cli", "s", "/t.jsonl"]


def test_capture_worker_posts_synchronously(monkeypatch):
    post = Mock()
    monkeypatch.setattr(memory, "post_session_to_api", post)
    monkeypatch.setattr("conduct_cli.hooks.base.detect_repo", lambda: "acme/repo")
    monkeypatch.setattr(sys, "argv", ["memory", "capture", "copilot-cli", "sid", ""])
    memory.main()
    post.assert_called_once_with("sid", None, "acme/repo", tool="copilot-cli", wait=True)


@pytest.fixture
def knowledge(monkeypatch):
    monkeypatch.setattr(memory, "search_team_memory", lambda *a, **k: [
        {"developer_id": "user_abcdefgh123", "summary": "Use 30s JWT leeway ✓"}])
    monkeypatch.setattr("conduct_cli.hooks.base.detect_repo", lambda: "acme/repo")


def test_codex_stop_spawns_capture_and_prints_nothing(monkeypatch, capsys):
    spawn = Mock()
    monkeypatch.setattr(memory, "spawn_capture", spawn)
    monkeypatch.setattr(session_usage.base, "detect_ai_tool", lambda: "codex-cli")
    session_usage.team_memory({"hook_event_name": "Stop", "session_id": "s", "transcript_path": "/t"}, "codex")
    spawn.assert_called_once_with("codex-cli", "s", "/t")
    assert capsys.readouterr().out == ""  # Codex Stop requires JSON or empty stdout.


def test_codex_session_start_injects_team_knowledge(knowledge, monkeypatch, capsys):
    monkeypatch.setattr(session_usage.base, "detect_ai_tool", lambda: "codex-cli")
    session_usage.team_memory({"hook_event_name": "SessionStart", "session_id": "s"}, "codex")
    out = capsys.readouterr().out
    assert out.isascii()  # cp1252-safe on Windows
    hook = json.loads(out)["hookSpecificOutput"]
    assert hook["hookEventName"] == "SessionStart"
    assert "Team knowledge" in hook["additionalContext"] and "JWT leeway ✓" in hook["additionalContext"]


def test_claude_lifecycle_usage_hook_does_not_double_capture(knowledge, monkeypatch, capsys):
    spawn = Mock()
    monkeypatch.setattr(memory, "spawn_capture", spawn)
    for event in ("Stop", "SessionStart"):
        session_usage.team_memory({"hook_event_name": event, "session_id": "s"}, "claude-code")
    spawn.assert_not_called()
    assert capsys.readouterr().out == ""


def test_copilot_session_start_returns_additional_context(knowledge, monkeypatch):
    monkeypatch.setattr("conduct_cli.hooks.copilot_usage.handle", Mock())
    result = copilot.run("session-start", Path("hook.py"), {"sessionId": str(uuid4())})
    assert set(result) == {"additionalContext"}
    assert "Team knowledge" in result["additionalContext"]


def test_copilot_session_start_without_matches_is_empty(monkeypatch):
    monkeypatch.setattr(memory, "team_knowledge_lines", list)
    monkeypatch.setattr("conduct_cli.hooks.copilot_usage.handle", Mock(side_effect=ValueError))
    assert copilot.run("session-start", Path("hook.py"), {"sessionId": "bad"}) == {}


def test_copilot_session_end_spawns_capture(monkeypatch):
    spawn = Mock()
    monkeypatch.setattr(memory, "spawn_capture", spawn)
    monkeypatch.setattr("conduct_cli.hooks.copilot_usage.handle", Mock())
    session = str(uuid4())
    assert copilot.run("session-end", Path("hook.py"), {"sessionId": session}) == {}
    spawn.assert_called_once_with("copilot-cli", session, None)


def test_copilot_main_prints_json(monkeypatch, capsys, knowledge):
    monkeypatch.setattr("conduct_cli.hooks.copilot_usage.handle", Mock())
    monkeypatch.setattr(sys, "argv", ["copilot", "session-start", "hook.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"sessionId": str(uuid4())})))
    copilot.main()
    assert "additionalContext" in json.loads(capsys.readouterr().out)
