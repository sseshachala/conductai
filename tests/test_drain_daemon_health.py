"""Tests for drain daemon stale-PID detection and ensure_drain_daemon restart logic."""
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import conduct_cli.hooks.base as base


# ── drain_daemon_status ────────────────────────────────────────────────────────

def test_status_dead_no_pid_file(tmp_path):
    with patch.object(base, "JOURNAL_PID_PATH", tmp_path / "drain.pid"):
        status, pid = base.drain_daemon_status()
    assert status == "dead"
    assert pid is None


def test_status_dead_process_gone(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text("999999999")  # non-existent PID
    with patch.object(base, "JOURNAL_PID_PATH", pid_file):
        status, pid = base.drain_daemon_status()
    assert status == "dead"
    assert pid is None


def test_status_running_fresh(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text(str(os.getpid()))  # current process — definitely alive
    # mtime is now → fresh
    with patch.object(base, "JOURNAL_PID_PATH", pid_file):
        status, pid = base.drain_daemon_status()
    assert status == "running"
    assert pid == os.getpid()


def test_status_stale_old_mtime(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text(str(os.getpid()))
    # backdate mtime beyond stale threshold
    old = time.time() - base._DAEMON_STALE_SECS - 60
    os.utime(pid_file, (old, old))
    with patch.object(base, "JOURNAL_PID_PATH", pid_file):
        status, pid = base.drain_daemon_status()
    assert status == "stale"
    assert pid == os.getpid()


def test_status_corrupt_pid_file(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text("not-a-number")
    with patch.object(base, "JOURNAL_PID_PATH", pid_file):
        status, pid = base.drain_daemon_status()
    assert status == "dead"
    assert pid is None


# ── ensure_drain_daemon ────────────────────────────────────────────────────────

def test_ensure_no_spawn_when_running(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text(str(os.getpid()))

    with patch.object(base, "JOURNAL_PID_PATH", pid_file), \
         patch.object(base, "subprocess") as mock_sub:
        base.ensure_drain_daemon(hook_module_path=Path("/fake/hook.py"))

    mock_sub.Popen.assert_not_called()


def test_ensure_spawns_when_dead(tmp_path):
    pid_file = tmp_path / "drain.pid"
    # no PID file → dead

    with patch.object(base, "JOURNAL_PID_PATH", pid_file), \
         patch.object(base, "subprocess") as mock_sub:
        base.ensure_drain_daemon(hook_module_path=Path("/fake/hook.py"))

    mock_sub.Popen.assert_called_once()


def test_ensure_kills_stale_and_spawns(tmp_path):
    pid_file = tmp_path / "drain.pid"
    pid_file.write_text(str(os.getpid()))
    old = time.time() - base._DAEMON_STALE_SECS - 60
    os.utime(pid_file, (old, old))

    fake_proc = MagicMock()
    fake_psutil = MagicMock()
    fake_psutil.pid_exists.return_value = True
    fake_psutil.Process.return_value = fake_proc

    with patch.object(base, "JOURNAL_PID_PATH", pid_file), \
         patch.object(base, "subprocess"), \
         patch.object(base, "_psutil", fake_psutil):
        base.ensure_drain_daemon(hook_module_path=Path("/fake/hook.py"))

    fake_proc.terminate.assert_called_once()


def test_ensure_no_spawn_without_hook_path(tmp_path):
    """hook_module_path=None → no spawn even when dead (test/debug mode)."""
    pid_file = tmp_path / "drain.pid"

    with patch.object(base, "JOURNAL_PID_PATH", pid_file), \
         patch.object(base, "subprocess") as mock_sub:
        base.ensure_drain_daemon(hook_module_path=None)

    mock_sub.Popen.assert_not_called()


# ── PID file touch in drain loop ───────────────────────────────────────────────

def test_pid_file_touched_after_flush(tmp_path):
    """run_drain_daemon touches the PID file after each flush so mtime stays fresh."""
    pid_file = tmp_path / "drain.pid"
    journal_dir = tmp_path / "journal"
    journal_dir.mkdir()

    # Write one fake journal entry that will fail to POST (no server)
    entry = journal_dir / "ev1.json"
    entry.write_text('{"api_url": "http://127.0.0.1:19999", "payload": "{}"}')

    before = time.time() - 5

    with patch.object(base, "JOURNAL_DIR", journal_dir), \
         patch.object(base, "JOURNAL_PID_PATH", pid_file):
        # Run just enough of the drain loop to hit the touch
        # Patch sleep to break out after first iteration
        call_count = [0]
        orig_sleep = time.sleep
        def fast_sleep(n):
            call_count[0] += 1
            if call_count[0] >= 2:
                raise KeyboardInterrupt
        with patch("time.sleep", fast_sleep):
            try:
                base.run_drain_daemon()
            except KeyboardInterrupt:
                pass

    if pid_file.exists():
        assert pid_file.stat().st_mtime >= before


# ── Policy refresh ─────────────────────────────────────────────────────────────

def test_refresh_policy_writes_file(tmp_path):
    """_refresh_policy_from_api writes API response to POLICY_PATH atomically."""
    import urllib.request as _ur
    from unittest.mock import MagicMock

    fake_policy = b'{"rules": [{"id": "r1"}]}'
    policy_path = tmp_path / "policy.json"

    fake_resp = MagicMock()
    fake_resp.read.return_value = fake_policy
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch.object(base, "POLICY_PATH", policy_path), \
         patch.object(base, "load_config", return_value={
             "workspace_id": "ws_test",
             "agent_token": "cond_agt_test",
             "api_url": "https://api.conductai.ai",
         }), \
         patch("urllib.request.urlopen", return_value=fake_resp):
        base._refresh_policy_from_api()

    assert policy_path.exists()
    assert policy_path.read_bytes() == fake_policy


def test_refresh_policy_skips_without_api_key(tmp_path):
    """_refresh_policy_from_api is a no-op when api_key is absent."""
    policy_path = tmp_path / "policy.json"

    with patch.object(base, "POLICY_PATH", policy_path), \
         patch.object(base, "load_config", return_value={"workspace_id": "ws_test"}), \
         patch("urllib.request.urlopen") as mock_open:
        base._refresh_policy_from_api()

    mock_open.assert_not_called()
    assert not policy_path.exists()


def test_refresh_policy_works_without_workspace_id(tmp_path):
    """_refresh_policy_from_api omits workspace_id param when not in config (org-level Guard)."""
    fake_policy = b'{"rules": []}'
    policy_path = tmp_path / "policy.json"

    fake_resp = MagicMock()
    fake_resp.read.return_value = fake_policy
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__ = MagicMock(return_value=False)

    with patch.object(base, "POLICY_PATH", policy_path), \
         patch.object(base, "load_config", return_value={"agent_token": "cond_agt_test"}), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        base._refresh_policy_from_api()

    called_url = mock_open.call_args[0][0].full_url
    assert "workspace_id" not in called_url
    assert policy_path.read_bytes() == fake_policy
