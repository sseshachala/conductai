"""
modal_session_runner — long-running IPC subprocess for ModalSession.

ModalSession spawns one instance of this process per Brain block execution.
Communication is JSON lines over stdin/stdout:

  stdin:  {"tool_name": "run_shell", "tool_input": {...}}
  stdout: {"result": "...", "working_dir": "/tmp/..."}

The process exits when it receives {"tool_name": "__exit__"} or stdin closes.

Running inside a Modal sandbox gives the Brain block a persistent container:
files written in one tool call are readable in the next.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile

_FORBIDDEN_SHELL_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"rm\s+-fr\s+/",
    r"mkfs",
    r"dd\s+if=",
    r":\(\)\{.*\}",
    r">\s*/dev/sd",
    r"chmod\s+777\s+/",
    r"chown.*root",
]

_tmpdir = tempfile.mkdtemp(prefix="conduct_modal_")
_working_dir: str = _tmpdir


def _read_file(path: str) -> str:
    if not path:
        return "Error: missing required parameter 'path'"
    try:
        with open(path) as f:
            content = f.read()
        return (content[:20_000] + "\n[... truncated]") if len(content) > 20_000 else content
    except Exception as e:
        return f"Error reading file: {e}"


def _write_file(path: str, content: str) -> str:
    if not path:
        return "Error: missing required parameter 'path'"
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _run_shell(command: str, working_dir: str | None = None, env: dict | None = None) -> str:
    global _working_dir
    if not command:
        return "Error: missing required parameter 'command'"
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command):
            return f"Refused: command matches forbidden pattern '{pattern}'"
    cwd = working_dir or _working_dir
    if working_dir:
        _working_dir = working_dir
    try:
        merged_env = {**os.environ, **(env or {})}
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True,
            timeout=120, cwd=cwd, env=merged_env,
        )
        output = result.stdout + result.stderr
        return (output[:10_000] + "\n[... truncated]") if len(output) > 10_000 else output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120s"
    except Exception as e:
        return f"Error running shell: {e}"


def _search_code(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    if not pattern:
        return "Error: missing required parameter 'pattern'"
    try:
        result = subprocess.run(
            ["grep", "-r", "--include", file_glob, "-n", pattern, path],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout
        return (output[:8_000] + "\n[... truncated]") if len(output) > 8_000 else output or "(no matches)"
    except Exception as e:
        return f"Error searching: {e}"


def _dispatch(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return _read_file(tool_input.get("path", ""))
    if tool_name == "write_file":
        return _write_file(tool_input.get("path", ""), tool_input.get("content", ""))
    if tool_name == "run_shell":
        return _run_shell(tool_input.get("command", ""), tool_input.get("working_dir"), tool_input.get("env"))
    if tool_name == "search_code":
        return _search_code(tool_input.get("pattern", ""), tool_input.get("path", "."), tool_input.get("file_glob", "*"))
    return f"Unknown tool: {tool_name}"


def main() -> None:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps({"result": "Error: invalid JSON"}) + "\n")
            sys.stdout.flush()
            continue

        if msg.get("tool_name") == "__exit__":
            break

        tool_name = msg.get("tool_name", "")
        tool_input = msg.get("tool_input", {})
        result = _dispatch(tool_name, tool_input)
        response = {"result": result, "working_dir": _working_dir}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
