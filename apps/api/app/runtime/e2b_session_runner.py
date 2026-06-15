"""
e2b_session_runner — persistent E2B sandbox IPC subprocess.

E2BSession spawns one instance of this process per Brain block. The E2B
API key is in this process's env only — never in the API worker env.

Creates ONE E2B sandbox at startup via REST API, then handles tool calls
by exec-ing commands into the sandbox so filesystem state persists across
tool calls within the same block.

Communication: JSON lines over stdin/stdout.
  stdin:  {"tool_name": "run_shell", "tool_input": {...}}
  stdout: {"result": "...", "working_dir": "/home/user"}
  exit:   {"tool_name": "__exit__"}

E2B REST API:
  POST   /sandboxes                          create sandbox
  POST   /sandboxes/{id}/commands            run command
  GET    /sandboxes/{id}/files?path=...      read file
  POST   /sandboxes/{id}/files?path=...      write file
  DELETE /sandboxes/{id}                     terminate sandbox
"""
from __future__ import annotations

import base64
import json
import os
import re
import shlex
import sys
import time

import httpx

E2B_API_BASE = "https://api.e2b.dev"
E2B_TEMPLATE  = "base"          # default sandbox template — has git, python3, node
CMD_TIMEOUT   = 120             # seconds per command
STARTUP_RETRIES = 5

from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS, dispatch_tool


def _headers(api_key: str) -> dict:
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def _create_sandbox(client: httpx.Client, api_key: str) -> str:
    resp = client.post(
        f"{E2B_API_BASE}/sandboxes",
        json={"templateID": E2B_TEMPLATE},
        headers=_headers(api_key),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["sandboxID"]


def _run_command(
    client: httpx.Client,
    api_key: str,
    sandbox_id: str,
    command: str,
    envs: dict | None = None,
    working_dir: str = "/home/user",
) -> str:
    payload: dict = {
        "cmd": command,
        "timeout": CMD_TIMEOUT,
        "cwd": working_dir,
    }
    if envs:
        payload["envs"] = envs

    resp = client.post(
        f"{E2B_API_BASE}/sandboxes/{sandbox_id}/commands",
        json=payload,
        headers=_headers(api_key),
        timeout=CMD_TIMEOUT + 10,
    )
    resp.raise_for_status()
    data = resp.json()
    stdout = data.get("stdout", "")
    stderr = data.get("stderr", "")
    return stdout + stderr


def _read_file(client: httpx.Client, api_key: str, sandbox_id: str, path: str) -> str:
    resp = client.get(
        f"{E2B_API_BASE}/sandboxes/{sandbox_id}/files",
        params={"path": path},
        headers=_headers(api_key),
        timeout=30,
    )
    if resp.status_code == 404:
        return f"Error: file not found: {path}"
    resp.raise_for_status()
    return resp.text


def _write_file(
    client: httpx.Client, api_key: str, sandbox_id: str, path: str, content: str
) -> str:
    resp = client.post(
        f"{E2B_API_BASE}/sandboxes/{sandbox_id}/files",
        params={"path": path},
        content=content.encode(),
        headers={**_headers(api_key), "Content-Type": "application/octet-stream"},
        timeout=30,
    )
    resp.raise_for_status()
    return f"Written {len(content)} bytes to {path}"


def _terminate_sandbox(client: httpx.Client, api_key: str, sandbox_id: str) -> None:
    try:
        client.delete(
            f"{E2B_API_BASE}/sandboxes/{sandbox_id}",
            headers=_headers(api_key),
            timeout=10,
        )
    except Exception:
        pass


def _dispatch(
    client: httpx.Client,
    api_key: str,
    sandbox_id: str,
    tool_name: str,
    tool_input: dict,
    working_dir: str,
) -> str:
    def _exec_shell(cmd: str, wd: str, env: dict | None) -> str:
        return _run_command(client, api_key, sandbox_id, cmd, envs=env or None, working_dir=wd)

    def _read(path: str) -> str:
        return _read_file(client, api_key, sandbox_id, path)

    def _write(path: str, content: str) -> str:
        parent = "/".join(path.split("/")[:-1])
        if parent:
            _run_command(client, api_key, sandbox_id, f"mkdir -p {shlex.quote(parent)}")
        return _write_file(client, api_key, sandbox_id, path, content)

    return dispatch_tool(tool_name, tool_input, working_dir,
                         exec_shell=_exec_shell, read_file=_read, write_file=_write)


def main() -> None:
    api_key = os.environ.get("E2B_API_KEY", "")
    if not api_key:
        sys.stderr.write("E2B_API_KEY not set\n")
        sys.exit(1)

    working_dir = "/home/user"

    with httpx.Client() as client:
        sandbox_id = _create_sandbox(client, api_key)

        # Write sandbox ID as first stdout line so E2BSession can terminate
        # the sandbox directly if this subprocess is force-killed.
        sys.stdout.write(json.dumps({"sandbox_id": sandbox_id}) + "\n")
        sys.stdout.flush()

        try:
            for raw in sys.stdin:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    sys.stdout.write(json.dumps({"result": "Error: invalid JSON"}) + "\n")
                    sys.stdout.flush()
                    continue

                if msg.get("tool_name") == "__exit__":
                    break

                tool_name = msg.get("tool_name", "")
                tool_input = msg.get("tool_input", {})
                result = _dispatch(client, api_key, sandbox_id, tool_name, tool_input, working_dir)

                if tool_name == "run_shell" and tool_input.get("working_dir"):
                    working_dir = tool_input["working_dir"]

                sys.stdout.write(json.dumps({"result": result, "working_dir": working_dir}) + "\n")
                sys.stdout.flush()
        finally:
            _terminate_sandbox(client, api_key, sandbox_id)


if __name__ == "__main__":
    main()
