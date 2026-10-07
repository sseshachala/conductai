"""Characterization test: run bundled paxel exactly as the callers do."""
import json

from conduct_cli import paxel_runner

SESSION = "11111111-2222-3333-4444-555555555555"


def _event(kind, ts, content, **extra):
    return {
        "type": kind, "sessionId": SESSION, "timestamp": ts, "cwd": "/tmp/demo-proj",
        "message": {"role": kind, "content": content, "model": "claude-opus-4-7"}, **extra,
    }


def _transcript():
    tool = {"type": "tool_use", "id": "t1", "name": "Edit",
            "input": {"file_path": "/tmp/demo-proj/app.py", "old_string": "a", "new_string": "b\nc"}}
    read = {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/tmp/demo-proj/app.py"}}
    return [
        _event("user", "2026-09-01T10:00:00Z", "please fix the failing test in app.py"),
        _event("assistant", "2026-09-01T10:00:20Z", [read]),
        _event("assistant", "2026-09-01T10:01:00Z", [tool]),
        _event("user", "2026-09-01T10:05:00Z", "thanks, now add a docstring"),
        _event("assistant", "2026-09-01T10:05:30Z", [tool]),
        _event("user", "2026-09-01T10:09:00Z", "ship it"),
    ]


def test_run_paxel_writes_outputs(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = home / ".claude" / "projects" / "-tmp-demo-proj"
    proj.mkdir(parents=True)
    (proj / f"{SESSION}.jsonl").write_text("\n".join(json.dumps(e) for e in _transcript()) + "\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    out = tmp_path / "out"
    out.mkdir()

    result = paxel_runner.run_paxel(out, timeout=120)

    assert result.returncode == 0, result.stderr
    for name in ("stats.json", "report.md", "narrative_input.md", "profile.html"):
        assert (out / name).exists(), f"{name} missing\n{result.stdout}\n{result.stderr}"
    stats = json.loads((out / "stats.json").read_text())
    assert stats["volume"]["total_sessions"] == 1
    assert stats["volume"]["total_prompts"] == 3
    assert dict(stats["tools"]["top_tools"])["Edit"] == 2
    assert "autonomy_score_0_100" in stats["autonomy"]
