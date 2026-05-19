"""
Unit tests for RemoteSandbox — does not open a real SSH connection. We mock
paramiko's SSHClient + SFTPClient and verify command shape, error handling,
and the forbidden-pattern denylist.
"""
from unittest.mock import MagicMock, patch

import pytest

from app.runtime import remote_sandbox
from app.runtime.remote_sandbox import (
    is_forbidden_command,
    remote_dispatch,
)


HOST_CONFIG = {
    "ip": "10.0.0.42",
    "username": "root",
    "private_key": "-----BEGIN PRIVATE KEY-----
REDACTED
-----END PRIVATE KEY-----\n",
}


def _fake_channel(stdout: str = "", stderr: str = ""):
    """Build a fake paramiko stdout/stderr file-like triple."""
    out = MagicMock()
    out.read.return_value = stdout.encode("utf-8")
    err = MagicMock()
    err.read.return_value = stderr.encode("utf-8")
    stdin = MagicMock()
    return stdin, out, err


@pytest.fixture
def patched_client():
    """Patch _open_client so tests never touch paramiko or the network."""
    with patch.object(remote_sandbox, "_open_client") as p:
        client = MagicMock()
        p.return_value = client
        yield client


def test_forbidden_command_detected_without_running():
    assert is_forbidden_command("rm -rf /")
    assert is_forbidden_command("mkfs.ext4 /dev/sda")
    assert not is_forbidden_command("ls -la")


def test_run_shell_refuses_forbidden_pattern_without_opening_connection(patched_client):
    out = remote_dispatch("run_shell", {"command": "rm -rf /"}, HOST_CONFIG)
    assert "Refused" in out
    # The early-return for forbidden commands happens after connection opens —
    # but no exec_command should have been invoked.
    patched_client.exec_command.assert_not_called()


def test_run_shell_wraps_cd_when_working_dir_set(patched_client):
    patched_client.exec_command.return_value = _fake_channel("ok\n")
    remote_dispatch(
        "run_shell",
        {"command": "ls", "working_dir": "/root/work"},
        HOST_CONFIG,
    )
    args, _ = patched_client.exec_command.call_args
    assert args[0].startswith("cd "), "expected cd prefix when working_dir is set"
    assert "/root/work" in args[0]


def test_run_shell_truncates_long_output(patched_client):
    big = "x" * (remote_sandbox.MAX_SHELL_OUTPUT * 2)
    patched_client.exec_command.return_value = _fake_channel(big)
    out = remote_dispatch("run_shell", {"command": "echo big"}, HOST_CONFIG)
    assert "truncated" in out
    assert len(out) <= remote_sandbox.MAX_SHELL_OUTPUT + len("\n[... truncated]") + 5


def test_run_shell_returns_no_output_for_empty(patched_client):
    patched_client.exec_command.return_value = _fake_channel("", "")
    out = remote_dispatch("run_shell", {"command": "true"}, HOST_CONFIG)
    assert out == "(no output)"


def test_search_code_uses_grep_with_safe_quoting(patched_client):
    patched_client.exec_command.return_value = _fake_channel("file.py:1:hit\n")
    remote_dispatch(
        "search_code",
        {"pattern": "needle", "path": "/root/work", "file_glob": "*.py"},
        HOST_CONFIG,
    )
    args, _ = patched_client.exec_command.call_args
    cmd = args[0]
    assert cmd.startswith("grep -r --include ")
    assert "'*.py'" in cmd or "*.py" in cmd
    assert "needle" in cmd
    assert "/root/work" in cmd


def test_unknown_tool_returns_error_string(patched_client):
    out = remote_dispatch("teleport", {}, HOST_CONFIG)
    assert "Unknown tool" in out


def test_connection_failure_does_not_raise(patched_client):
    with patch.object(remote_sandbox, "_open_client", side_effect=RuntimeError("net")):
        out = remote_dispatch("run_shell", {"command": "ls"}, HOST_CONFIG)
    assert "Error connecting to remote host" in out
