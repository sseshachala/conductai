"""Tests for conduct_cli.log_util — error interceptor + post path (#718)."""
from __future__ import annotations

import pytest

from conduct_cli import log_util


def test_interceptor_catches_exception_and_posts(monkeypatch):
    captured = {}

    def _fake_post(event_type, message, tb, ctx, *, wait=False):
        captured["event_type"] = event_type
        captured["message"] = message
        captured["tb"] = tb
        captured["wait"] = wait

    monkeypatch.setattr(log_util, "_post_event", _fake_post)

    def _boom():
        raise ValueError("kaboom")

    wrapped = log_util.install_error_interceptor(_boom)
    with pytest.raises(SystemExit) as ex:
        wrapped()
    assert ex.value.code == 1
    assert captured["event_type"] == "error"
    assert "ValueError" in captured["message"]
    assert "kaboom" in captured["message"]
    assert captured["tb"] is not None
    assert captured["wait"] is True


def test_interceptor_passes_through_systemexit(monkeypatch):
    monkeypatch.setattr(log_util, "_post_event", lambda *a, **k: None)

    def _exit_clean():
        raise SystemExit(0)

    wrapped = log_util.install_error_interceptor(_exit_clean)
    with pytest.raises(SystemExit) as ex:
        wrapped()
    assert ex.value.code == 0


def test_post_skipped_when_no_creds(monkeypatch, tmp_path):
    """No ~/.conductguard/config.json → no POST attempted."""
    monkeypatch.setattr(log_util, "_CONFIG", tmp_path / "missing.json")
    log_util._read_creds.cache_clear()

    called = {"urlopen": 0}
    def _fake_urlopen(*a, **k):
        called["urlopen"] += 1
    monkeypatch.setattr(log_util.urllib.request, "urlopen", _fake_urlopen)

    log_util._post_event_sync("error", "boom", None, {})
    assert called["urlopen"] == 0


def test_local_file_gets_jsonl_line(monkeypatch, tmp_path):
    """log() writes a JSONL line for warn/error to the local file."""
    import json
    log_file = tmp_path / "events.jsonl"
    monkeypatch.setattr(log_util, "_LOG_FILE", log_file)
    monkeypatch.setattr(log_util, "_post_event", lambda *a, **k: None)

    log_util.log("error", "boom-on-disk", run="r1")

    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["event_type"] == "error"
    assert row["message"]    == "boom-on-disk"
    assert row["tool"]       == log_util.TOOL
    assert row["context"]    == {"run": "r1"}


def test_local_file_rotates_when_oversize(monkeypatch, tmp_path):
    """When the file passes _MAX_BYTES, current file rotates to .1 and a fresh file starts."""
    from pathlib import Path
    log_file = tmp_path / "events.jsonl"
    monkeypatch.setattr(log_util, "_LOG_FILE", log_file)
    monkeypatch.setattr(log_util, "_MAX_BYTES", 200)  # tiny cap so the test rotates quickly
    monkeypatch.setattr(log_util, "_post_event", lambda *a, **k: None)

    # First write — creates the file
    log_util.log("error", "first")
    assert log_file.exists()

    # Fill the file past the cap so the next write triggers rotation
    log_file.write_text("x" * 300)

    log_util.log("error", "after-rotation")

    rotated = Path(str(log_file) + ".1")
    assert rotated.exists(), "rotation should produce events.jsonl.1"
    assert log_file.exists() and log_file.stat().st_size > 0
    # Newest event lives in the current file, not the rotated one
    assert "after-rotation" in log_file.read_text()


def test_local_file_persists_traceback_on_interceptor(monkeypatch, tmp_path):
    """Unhandled exception → traceback lands in the local file."""
    import json
    log_file = tmp_path / "events.jsonl"
    monkeypatch.setattr(log_util, "_LOG_FILE", log_file)
    monkeypatch.setattr(log_util, "_post_event", lambda *a, **k: None)

    def _boom():
        raise RuntimeError("disk-trace")

    wrapped = log_util.install_error_interceptor(_boom)
    with pytest.raises(SystemExit):
        wrapped()

    rows = [json.loads(l) for l in log_file.read_text().splitlines()]
    assert any(
        r["event_type"] == "error"
        and "RuntimeError" in r["message"]
        and r["traceback"] and "disk-trace" in r["traceback"]
        for r in rows
    )
