"""conductguard-mcp stdio smoke test — runs in cli-matrix on every OS x Python combo.

Spawns the installed `conductguard-mcp` binary, sends `initialize` + `tools/list`
over stdin, asserts the responses parse and expose the standard tool set. The
CLI matrix would catch packaging regressions, stdio-loop crashes, or a broken
initialize handshake that would otherwise only surface in Claude Desktop.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(
    shutil.which("conductguard-mcp") is None,
    reason="conductguard-mcp not on PATH (install the package first)",
)


def _run(messages, timeout=8):
    """Feed newline-delimited JSON-RPC messages, collect newline-delimited responses."""
    payload = "\n".join(json.dumps(m) for m in messages) + "\n"
    proc = subprocess.run(
        ["conductguard-mcp", "--workspace", "00000000-0000-0000-0000-000000000000",
         "--token", "dummy-for-stdio-smoke"],
        input=payload,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return proc, [json.loads(ln) for ln in lines]


def test_initialize_returns_protocol_and_capabilities():
    proc, replies = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "cli-matrix"}}},
    ])
    assert proc.returncode == 0, "conductguard-mcp exited " + str(proc.returncode) + ": " + proc.stderr[-400:]
    assert len(replies) == 1
    result = replies[0]["result"]
    assert "protocolVersion" in result
    assert "capabilities" in result and "tools" in result["capabilities"]


def test_tools_list_exposes_guard_tools():
    proc, replies = _run([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "cli-matrix"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ])
    assert proc.returncode == 0
    tool_lists = [r for r in replies if isinstance(r, dict) and r.get("id") == 2]
    assert tool_lists, "no tools/list response found in: " + str(replies)
    tools = tool_lists[0]["result"]["tools"]
    names = {t["name"] for t in tools}
    assert {"guard_check", "guard_activity"}.issubset(names), (
        "expected the standard guard tool set, got: " + str(sorted(names))
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
