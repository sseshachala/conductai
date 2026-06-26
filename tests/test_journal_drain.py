"""Tests for #855-B: journal append + drain daemon logic."""
from __future__ import annotations
import json
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

import conduct_cli.hook_template as ht


# ── helpers ──────────────────────────────────────────────────────────────────

def _patch_journal(tmp_path: Path):
    """Return context managers that redirect JOURNAL_DIR/PID_PATH to tmp_path."""
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    return (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
    )


# ── _journal_append ───────────────────────────────────────────────────────────

def test_journal_append_creates_file(tmp_path):
    p1, p2 = _patch_journal(tmp_path)
    with p1, p2:
        ht._journal_append('{"foo": 1}', "https://api.test")
        journal_dir = tmp_path / "journal"
        files = list(journal_dir.glob("*.json"))
        assert len(files) == 1
        entry = json.loads(files[0].read_text())
        assert entry["payload"] == '{"foo": 1}'
        assert entry["api_url"] == "https://api.test"


def test_journal_append_no_tmp_files_left(tmp_path):
    p1, p2 = _patch_journal(tmp_path)
    with p1, p2:
        ht._journal_append("{}", "https://api.test")
        journal_dir = tmp_path / "journal"
        assert not list(journal_dir.glob("*.tmp"))


# ── _run_drain_daemon ─────────────────────────────────────────────────────────

def _write_journal_entry(journal_dir: Path, payload: str, api_url: str) -> Path:
    journal_dir.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}_0000.json"
    f = journal_dir / name
    f.write_text(json.dumps({"api_url": api_url, "payload": payload}))
    return f


def test_drain_posts_and_deletes_on_success(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    entry = _write_journal_entry(journal_dir, '{"x":1}', "https://api.test")

    mock_resp = MagicMock()
    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("urllib.request.urlopen", return_value=mock_resp),
        patch("time.sleep"),  # skip sleeps
    ):
        ht._run_drain_daemon()

    assert not entry.exists(), "file should be deleted after successful POST"


def test_drain_leaves_file_on_network_failure(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    entry = _write_journal_entry(journal_dir, '{"x":1}', "https://api.test")

    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("urllib.request.urlopen", side_effect=OSError("network down")),
        patch("time.sleep"),  # skip sleeps so daemon exits after 3 all-fail scans
    ):
        ht._run_drain_daemon()

    assert entry.exists(), "file should survive a failed POST"


def test_drain_exits_after_three_empty_scans(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    journal_dir.mkdir(parents=True, exist_ok=True)
    sleep_calls = []

    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)),
    ):
        ht._run_drain_daemon()

    assert len(sleep_calls) == 3, "should sleep exactly 3 times before exiting"


# ── _ensure_drain_daemon ──────────────────────────────────────────────────────

def test_ensure_drain_skips_spawn_when_alive(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    journal_dir.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()))  # our own PID — definitely alive

    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("subprocess.Popen") as mock_popen,
    ):
        ht._ensure_drain_daemon()
        mock_popen.assert_not_called()


def test_ensure_drain_spawns_when_pid_missing(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    journal_dir.mkdir(parents=True, exist_ok=True)
    # no pid file written

    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("subprocess.Popen") as mock_popen,
    ):
        ht._ensure_drain_daemon()
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[-1] == "drain"


def test_ensure_drain_spawns_when_pid_stale(tmp_path):
    journal_dir = tmp_path / "journal"
    pid_path = journal_dir / "drain.pid"
    journal_dir.mkdir(parents=True, exist_ok=True)
    pid_path.write_text("99999999")  # almost certainly dead

    with (
        patch.object(ht, "JOURNAL_DIR", journal_dir),
        patch.object(ht, "JOURNAL_PID_PATH", pid_path),
        patch("subprocess.Popen") as mock_popen,
    ):
        ht._ensure_drain_daemon()
        mock_popen.assert_called_once()
