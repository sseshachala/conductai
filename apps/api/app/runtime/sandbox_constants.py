from __future__ import annotations

import re
import shlex
from typing import Callable

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


def dispatch_tool(
    tool_name: str,
    tool_input: dict,
    working_dir: str,
    *,
    exec_shell: Callable[[str, str, dict | None], str],
    read_file: Callable[[str], str],
    write_file: Callable[[str, str], str],
) -> str:
    """
    Shared dispatch for sandbox tool calls — validation, forbidden-pattern check,
    and truncation are identical across Modal, E2B, and remote runners.

    Callers supply three execution callbacks that differ per backend:
      exec_shell(command, working_dir, env) -> str
      read_file(path) -> str
      write_file(path, content) -> str
    """
    if tool_name == "read_file":
        path = tool_input.get("path", "")
        if not path:
            return "Error: missing required parameter 'path'"
        out = read_file(path)
        return (out[:20_000] + "\n[... truncated]") if len(out) > 20_000 else out

    if tool_name == "write_file":
        path = tool_input.get("path", "")
        content = tool_input.get("content", "")
        if not path:
            return "Error: missing required parameter 'path'"
        return write_file(path, content)

    if tool_name == "run_shell":
        command = tool_input.get("command", "")
        if not command:
            return "Error: missing required parameter 'command'"
        for pattern in _FORBIDDEN_SHELL_PATTERNS:
            if re.search(pattern, command):
                return f"Refused: command matches forbidden pattern '{pattern}'"
        wd = tool_input.get("working_dir") or working_dir
        env = tool_input.get("env") or None
        out = exec_shell(command, wd, env)
        return (out[:10_000] + "\n[... truncated]") if len(out) > 10_000 else out or "(no output)"

    if tool_name == "search_code":
        pattern = tool_input.get("pattern", "")
        if not pattern:
            return "Error: missing required parameter 'pattern'"
        path = tool_input.get("path", ".")
        file_glob = tool_input.get("file_glob", "*")
        cmd = f"grep -r --include={shlex.quote(file_glob)} -n {shlex.quote(pattern)} {shlex.quote(path)}"
        out = exec_shell(cmd, working_dir, None)
        return (out[:8_000] + "\n[... truncated]") if len(out) > 8_000 else out or "(no matches)"

    return f"Unknown tool: {tool_name}"
