"""
Tests for sandbox_session — LocalSession, ModalSession (mocked IPC), RemoteSession (mocked SSH).

These run entirely without Modal credentials, SSH targets, or a database.
The goal: verify that each backend correctly dispatches tools, tracks working_dir,
preserves filesystem state across calls (persistence), and cleans up on close().
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from app.runtime.sandbox_session import LocalSession, ModalSession, RemoteSession, create_session


# ─────────────────────────────────────────────────────────────────────────────
# LocalSession
# ─────────────────────────────────────────────────────────────────────────────

class TestLocalSession:
    def test_write_then_read_file_persists(self):
        """File written in turn 1 is readable in turn 2 — core persistence guarantee."""
        s = LocalSession()
        try:
            path = os.path.join(s.working_dir, "hello.txt")
            s.dispatch("write_file", {"path": path, "content": "hello world"})
            result = s.dispatch("read_file", {"path": path})
            assert result == "hello world"
        finally:
            s.close()

    def test_run_shell_creates_file_readable_in_next_call(self):
        """Shell command output (file creation) persists to next tool call."""
        s = LocalSession()
        try:
            out_path = os.path.join(s.working_dir, "stamp.txt")
            s.dispatch("run_shell", {"command": f"echo persistent > {out_path}"})
            content = s.dispatch("read_file", {"path": out_path})
            assert "persistent" in content
        finally:
            s.close()

    def test_working_dir_updates_when_run_shell_sets_it(self):
        s = LocalSession()
        try:
            with tempfile.TemporaryDirectory() as td:
                s.dispatch("run_shell", {"command": "pwd", "working_dir": td})
                assert s.working_dir == td
        finally:
            s.close()

    def test_run_shell_uses_tracked_working_dir_for_subsequent_calls(self):
        """After working_dir is set, subsequent shell calls default to that dir."""
        s = LocalSession()
        try:
            subdir = os.path.join(s.working_dir, "work")
            os.makedirs(subdir)
            s.dispatch("run_shell", {"command": "pwd", "working_dir": subdir})
            # Next call without explicit working_dir should still land in subdir
            result = s.dispatch("run_shell", {"command": "pwd"})
            assert subdir in result
        finally:
            s.close()

    def test_run_shell_refuses_forbidden_rm_rf(self):
        s = LocalSession()
        try:
            result = s.dispatch("run_shell", {"command": "rm -rf /"})
            assert "Refused" in result
        finally:
            s.close()

    def test_run_shell_refuses_fork_bomb(self):
        s = LocalSession()
        try:
            result = s.dispatch("run_shell", {"command": ":(){:|:&};:"})
            assert "Refused" in result
        finally:
            s.close()

    def test_run_shell_env_vars_injected(self):
        s = LocalSession()
        try:
            result = s.dispatch("run_shell", {
                "command": "echo $MY_VAR",
                "env": {"MY_VAR": "injected"},
            })
            assert "injected" in result
        finally:
            s.close()

    def test_read_file_missing_path_returns_error(self):
        s = LocalSession()
        try:
            result = s.dispatch("read_file", {})
            assert "missing" in result.lower() or "error" in result.lower()
        finally:
            s.close()

    def test_read_file_nonexistent_returns_error(self):
        s = LocalSession()
        try:
            result = s.dispatch("read_file", {"path": "/tmp/does_not_exist_xyz_abc.txt"})
            assert "Error" in result
        finally:
            s.close()

    def test_read_file_truncates_at_20k(self):
        s = LocalSession()
        try:
            path = os.path.join(s.working_dir, "big.txt")
            s.dispatch("write_file", {"path": path, "content": "x" * 25_000})
            result = s.dispatch("read_file", {"path": path})
            assert "truncated" in result
            assert len(result) <= 20_050  # 20k + truncation suffix
        finally:
            s.close()

    def test_run_shell_truncates_at_10k(self):
        s = LocalSession()
        try:
            result = s.dispatch("run_shell", {"command": "python3 -c \"print('y'*15000)\""})
            assert "truncated" in result
        finally:
            s.close()

    def test_search_code_finds_pattern(self):
        s = LocalSession()
        try:
            path = os.path.join(s.working_dir, "src.py")
            s.dispatch("write_file", {"path": path, "content": "def my_function():\n    pass\n"})
            result = s.dispatch("search_code", {
                "pattern": "my_function",
                "path": s.working_dir,
                "file_glob": "*.py",
            })
            assert "my_function" in result
        finally:
            s.close()

    def test_search_code_no_matches(self):
        s = LocalSession()
        try:
            result = s.dispatch("search_code", {
                "pattern": "xyzzy_nothere",
                "path": s.working_dir,
            })
            assert "(no matches)" in result
        finally:
            s.close()

    def test_unknown_tool_returns_error(self):
        s = LocalSession()
        try:
            result = s.dispatch("teleport", {})
            assert "Unknown tool" in result
        finally:
            s.close()

    def test_close_removes_tmpdir(self):
        s = LocalSession()
        tmpdir = s._tmpdir
        assert os.path.exists(tmpdir)
        s.close()
        assert not os.path.exists(tmpdir)

    def test_capture_artifacts_returns_empty_outside_git(self):
        s = LocalSession()
        try:
            files, stat = s.capture_artifacts()
            assert files == []
            assert stat == ""
        finally:
            s.close()

    def test_capture_artifacts_in_git_repo(self):
        """Create a real git repo, modify a file, verify capture_artifacts sees the diff."""
        s = LocalSession()
        try:
            repo = s.working_dir
            subprocess.run(["git", "init", repo], capture_output=True)
            subprocess.run(["git", "-C", repo, "config", "user.email", "test@test.com"], capture_output=True)
            subprocess.run(["git", "-C", repo, "config", "user.name", "Test"], capture_output=True)
            fpath = os.path.join(repo, "file.py")
            Path(fpath).write_text("original\n")
            subprocess.run(["git", "-C", repo, "add", "."], capture_output=True)
            subprocess.run(["git", "-C", repo, "commit", "-m", "init"], capture_output=True)
            # Modify the file — git diff --stat HEAD should see it
            Path(fpath).write_text("modified\n")
            files, stat = s.capture_artifacts()
            assert any(f["path"] == "file.py" for f in files)
            assert stat != ""
        finally:
            s.close()


# ─────────────────────────────────────────────────────────────────────────────
# ModalSession — subprocess IPC mocked
# ─────────────────────────────────────────────────────────────────────────────

def _make_modal_proc(responses: list[dict]) -> MagicMock:
    """
    Build a fake Popen object whose stdout.readline() returns canned JSON responses.
    Each entry in `responses` is one round-trip reply dict.
    """
    proc = MagicMock()
    proc.stdin = MagicMock()
    lines = iter(json.dumps(r) + "\n" for r in responses)
    proc.stdout.readline = lambda: next(lines, "")
    return proc


class TestModalSession:
    def _session(self, responses: list[dict]) -> ModalSession:
        s = ModalSession("fake_id", "fake_secret")
        proc = _make_modal_proc(responses)
        with patch("subprocess.Popen", return_value=proc):
            # Trigger _ensure_started by calling dispatch once — we'll handle
            # this by patching Popen before the first dispatch call in each test.
            s._proc = proc
            s._started = True
        return s

    def test_dispatch_sends_json_to_stdin_and_reads_response(self):
        s = ModalSession("id", "secret")
        proc = _make_modal_proc([{"result": "hello output", "working_dir": "/tmp/work"}])
        s._proc = proc
        s._started = True

        result = s.dispatch("run_shell", {"command": "echo hello"})

        assert result == "hello output"
        written = proc.stdin.write.call_args[0][0]
        payload = json.loads(written.strip())
        assert payload["tool_name"] == "run_shell"
        assert payload["tool_input"]["command"] == "echo hello"

    def test_dispatch_updates_working_dir_from_response(self):
        s = ModalSession("id", "secret")
        proc = _make_modal_proc([{"result": "ok", "working_dir": "/tmp/repo"}])
        s._proc = proc
        s._started = True

        s.dispatch("run_shell", {"command": "ls", "working_dir": "/tmp/repo"})
        assert s.working_dir == "/tmp/repo"

    def test_dispatch_returns_error_on_process_termination(self):
        """If the subprocess stdout is empty (process died), return a clear error."""
        s = ModalSession("id", "secret")
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.stdout.readline.return_value = ""  # process died
        s._proc = proc
        s._started = True

        result = s.dispatch("run_shell", {"command": "ls"})
        assert "terminated" in result.lower() or "error" in result.lower()

    def test_close_sends_exit_sentinel(self):
        s = ModalSession("id", "secret")
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.wait.return_value = 0
        s._proc = proc
        s._started = True

        s.close()

        written = proc.stdin.write.call_args[0][0]
        payload = json.loads(written.strip())
        assert payload["tool_name"] == "__exit__"

    def test_close_kills_proc_if_wait_times_out(self):
        s = ModalSession("id", "secret")
        proc = MagicMock()
        proc.stdin = MagicMock()
        proc.wait.side_effect = subprocess.TimeoutExpired("cmd", 10)
        s._proc = proc
        s._started = True

        s.close()  # should not raise
        proc.kill.assert_called_once()

    def test_capture_artifacts_dispatches_git_diff(self):
        s = ModalSession("id", "secret")
        diff_stat = "file.py | 3 +++"
        proc = _make_modal_proc([
            {"result": diff_stat, "working_dir": "/tmp/repo"},
        ])
        s._proc = proc
        s._started = True
        s.working_dir = "/tmp/repo"

        files, stat = s.capture_artifacts()

        assert stat == diff_stat
        assert any(f["path"] == "file.py" for f in files)

    def test_capture_artifacts_returns_empty_when_no_working_dir(self):
        s = ModalSession("id", "secret")
        s._started = False
        s.working_dir = None
        files, stat = s.capture_artifacts()
        assert files == []
        assert stat == ""

    def test_ensure_started_spawns_modal_session_runner(self):
        s = ModalSession("tok_id", "tok_secret")
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            mock_popen.return_value.stdin = MagicMock()
            s._ensure_started()

        mock_popen.assert_called_once()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        assert "modal_session_runner" in " ".join(cmd)
        assert kwargs["env"]["MODAL_TOKEN_ID"] == "tok_id"
        assert kwargs["env"]["MODAL_TOKEN_SECRET"] == "tok_secret"
        # Credentials must NOT be in the API worker env — verify isolation
        assert os.environ.get("MODAL_TOKEN_ID") != "tok_id"

    def test_ensure_started_only_spawns_once(self):
        s = ModalSession("id", "secret")
        proc = MagicMock()
        proc.stdin = MagicMock()
        with patch("subprocess.Popen", return_value=proc) as mock_popen:
            s._ensure_started()
            s._ensure_started()
            s._ensure_started()
        mock_popen.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# RemoteSession — paramiko mocked via _open_client
# ─────────────────────────────────────────────────────────────────────────────

HOST_CONFIG = {
    "ip": "10.0.0.99",
    "username": "root",
    "private_key": "-----BEGIN PRIVATE KEY-----
REDACTED
-----END PRIVATE KEY-----\n",
}


def _exec_channel(stdout: str = "", stderr: str = ""):
    out = MagicMock()
    out.read.return_value = stdout.encode()
    err = MagicMock()
    err.read.return_value = stderr.encode()
    return MagicMock(), out, err


class TestRemoteSession:
    @pytest.fixture
    def client(self):
        return MagicMock()

    @pytest.fixture
    def session(self, client):
        s = RemoteSession(HOST_CONFIG)
        s._client = client  # inject already-connected client
        return s

    def test_run_shell_uses_persistent_client(self, session, client):
        client.exec_command.return_value = _exec_channel("output\n")
        result = session.dispatch("run_shell", {"command": "echo hi"})
        client.exec_command.assert_called_once()
        assert "output" in result

    def test_multiple_dispatches_reuse_same_client(self, session, client):
        client.exec_command.return_value = _exec_channel("ok")
        session.dispatch("run_shell", {"command": "ls"})
        session.dispatch("run_shell", {"command": "pwd"})
        assert client.exec_command.call_count == 2

    def test_ensure_connected_called_once_not_twice(self, client):
        """_ensure_connected should open exactly one SSH connection per session."""
        s = RemoteSession(HOST_CONFIG)
        from app.runtime import remote_sandbox as rsb
        with patch.object(rsb, "_open_client", return_value=client) as mock_open:
            client.exec_command.return_value = _exec_channel("a")
            s.dispatch("run_shell", {"command": "a"})
            s.dispatch("run_shell", {"command": "b"})
        mock_open.assert_called_once()

    def test_working_dir_tracked_from_run_shell(self, session, client):
        client.exec_command.return_value = _exec_channel("ok")
        session.dispatch("run_shell", {"command": "ls", "working_dir": "/root/project"})
        assert session.working_dir == "/root/project"

    def test_working_dir_not_overwritten_by_non_shell_tool(self, session, client):
        session.working_dir = "/existing/dir"
        # SFTP mock for read_file
        sftp = MagicMock()
        sftp.file.return_value.__enter__ = MagicMock(return_value=sftp.file.return_value)
        sftp.file.return_value.__exit__ = MagicMock(return_value=False)
        sftp.file.return_value.read.return_value = b"content"
        client.open_sftp.return_value = sftp
        session.dispatch("read_file", {"path": "/some/file.txt"})
        assert session.working_dir == "/existing/dir"

    def test_connection_failure_returns_error_string(self):
        s = RemoteSession(HOST_CONFIG)
        from app.runtime import remote_sandbox as rsb
        with patch.object(rsb, "_open_client", side_effect=RuntimeError("refused")):
            result = s.dispatch("run_shell", {"command": "ls"})
        assert "Error connecting" in result

    def test_dispatch_ssh_error_returns_error_string(self, session, client):
        """If exec_command raises, _remote_run_shell catches it and returns an error string."""
        client.exec_command.side_effect = OSError("connection reset")
        result = session.dispatch("run_shell", {"command": "ls"})
        assert "Error" in result or "error" in result.lower()

    def test_close_calls_client_close(self, session, client):
        session.close()
        client.close.assert_called_once()

    def test_close_handles_already_none_client(self):
        s = RemoteSession(HOST_CONFIG)
        s._client = None
        s.close()  # should not raise

    def test_capture_artifacts_empty_when_no_working_dir(self, session):
        session.working_dir = None
        files, stat = session.capture_artifacts()
        assert files == []
        assert stat == ""

    def test_capture_artifacts_parses_git_diff_stat(self, session, client):
        diff_output = "app/main.py | 5 ++---\nREADME.md | 1 +\n2 files changed, 4 insertions(+), 2 deletions(-)\n"
        client.exec_command.return_value = _exec_channel(diff_output)
        session.working_dir = "/root/project"
        files, stat = session.capture_artifacts()
        paths = [f["path"] for f in files]
        assert "app/main.py" in paths
        assert "README.md" in paths

    def test_forbidden_command_refused_without_ssh_call(self, session, client):
        from app.runtime import remote_sandbox as rsb
        result = session.dispatch("run_shell", {"command": "rm -rf /"})
        # RemoteSession delegates to _remote_run_shell which checks the denylist
        assert "Refused" in result
        client.exec_command.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# create_session factory
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateSession:
    def test_returns_remote_session_when_remote_host_set(self):
        session = create_session({"ip": "1.2.3.4"}, {})
        assert isinstance(session, RemoteSession)

    def test_returns_modal_session_when_modal_creds_present(self):
        creds = {"modal": {"token_id": "id", "token_secret": "secret"}}
        session = create_session(None, creds)
        assert isinstance(session, ModalSession)

    def test_returns_local_session_as_fallback(self):
        session = create_session(None, {})
        assert isinstance(session, LocalSession)
        session.close()

    def test_remote_host_takes_priority_over_modal_creds(self):
        creds = {"modal": {"token_id": "id", "token_secret": "secret"}}
        session = create_session({"ip": "1.2.3.4"}, creds)
        assert isinstance(session, RemoteSession)

    def test_empty_remote_host_falls_through_to_modal(self):
        creds = {"modal": {"token_id": "id", "token_secret": "secret"}}
        session = create_session({}, creds)  # no ip key
        assert isinstance(session, ModalSession)

    def test_partial_modal_creds_falls_through_to_local(self):
        creds = {"modal": {"token_id": "id"}}  # missing token_secret
        session = create_session(None, creds)
        assert isinstance(session, LocalSession)
        session.close()
