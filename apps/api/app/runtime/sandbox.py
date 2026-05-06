"""
Isolated execution sandbox for Brain block tool calls.

When MODAL_TOKEN_ID + MODAL_TOKEN_SECRET are set, each Brain block run
dispatches file/shell tools into an ephemeral Modal container — fully isolated,
destroyed after the block completes.

When those env vars are NOT set (local dev), falls back to direct subprocess
execution on the host (existing behaviour).
"""
import logging
import os
import re
import subprocess

log = logging.getLogger(__name__)

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

_modal_available = bool(os.environ.get("MODAL_TOKEN_ID") and os.environ.get("MODAL_TOKEN_SECRET"))


# ── Local fallback (dev mode) ─────────────────────────────────────────────────

def _local_read_file(path: str) -> str:
    try:
        with open(path) as f:
            content = f.read()
        return content[:20_000] + "\n[... truncated]" if len(content) > 20_000 else content
    except Exception as e:
        return f"Error reading file: {e}"


def _local_write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _local_run_shell(command: str, working_dir: str | None = None) -> str:
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command):
            return f"Refused: command matches forbidden pattern '{pattern}'"
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120, cwd=working_dir,
        )
        output = result.stdout + result.stderr
        return (output[:10_000] + "\n[... truncated]") if len(output) > 10_000 else output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 120s"
    except Exception as e:
        return f"Error running shell: {e}"


def _local_search_code(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    try:
        result = subprocess.run(
            ["grep", "-r", "--include", file_glob, "-n", pattern, path],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout
        return (output[:8_000] + "\n[... truncated]") if len(output) > 8_000 else output or "(no matches)"
    except Exception as e:
        return f"Error searching: {e}"


# ── Modal sandbox (production) ────────────────────────────────────────────────

def _modal_dispatch(tool_name: str, tool_input: dict) -> str:
    """Dispatch a single tool call into a Modal sandbox container."""
    try:
        import modal  # type: ignore[import]

        app = modal.App.lookup("delegator-brain-sandbox", create_if_missing=True)

        @app.function(
            timeout=120,
            cpu=1,
            memory=512,
            retries=0,
        )
        def _run_tool_in_sandbox(name: str, inputs: dict) -> str:
            import os, re, subprocess  # noqa: F401

            forbidden = [
                r"rm\s+-rf\s+/", r"rm\s+-fr\s+/", r"mkfs", r"dd\s+if=",
                r":\(\)\{.*\}", r">\s*/dev/sd", r"chmod\s+777\s+/", r"chown.*root",
            ]

            if name == "read_file":
                try:
                    with open(inputs["path"]) as f:
                        c = f.read()
                    return c[:20_000] + "\n[... truncated]" if len(c) > 20_000 else c
                except Exception as e:
                    return f"Error: {e}"

            if name == "write_file":
                try:
                    os.makedirs(os.path.dirname(os.path.abspath(inputs["path"])), exist_ok=True)
                    with open(inputs["path"], "w") as f:
                        f.write(inputs["content"])
                    return f"Written {len(inputs['content'])} bytes to {inputs['path']}"
                except Exception as e:
                    return f"Error: {e}"

            if name == "run_shell":
                cmd = inputs["command"]
                for p in forbidden:
                    if re.search(p, cmd):
                        return f"Refused: matches forbidden pattern '{p}'"
                try:
                    r = subprocess.run(
                        cmd, shell=True, capture_output=True, text=True,
                        timeout=110, cwd=inputs.get("working_dir"),
                    )
                    out = r.stdout + r.stderr
                    return (out[:10_000] + "\n[... truncated]") if len(out) > 10_000 else out or "(no output)"
                except subprocess.TimeoutExpired:
                    return "Error: timed out"
                except Exception as e:
                    return f"Error: {e}"

            if name == "search_code":
                try:
                    r = subprocess.run(
                        ["grep", "-r", "--include", inputs.get("file_glob", "*"), "-n",
                         inputs["pattern"], inputs.get("path", ".")],
                        capture_output=True, text=True, timeout=15,
                    )
                    out = r.stdout
                    return (out[:8_000] + "\n[... truncated]") if len(out) > 8_000 else out or "(no matches)"
                except Exception as e:
                    return f"Error: {e}"

            return f"Unknown tool: {name}"

        with modal.enable_output():
            return _run_tool_in_sandbox.remote(tool_name, tool_input)

    except Exception as e:
        log.warning("Modal dispatch failed, falling back to local: %s", e)
        return _dispatch_local(tool_name, tool_input)


# ── Public interface ──────────────────────────────────────────────────────────

def _dispatch_local(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        return _local_read_file(tool_input["path"])
    if tool_name == "write_file":
        return _local_write_file(tool_input["path"], tool_input["content"])
    if tool_name == "run_shell":
        return _local_run_shell(tool_input["command"], tool_input.get("working_dir"))
    if tool_name == "search_code":
        return _local_search_code(
            tool_input["pattern"],
            tool_input.get("path", "."),
            tool_input.get("file_glob", "*"),
        )
    return f"Unknown tool: {tool_name}"


def dispatch_brain_tool(tool_name: str, tool_input: dict) -> str:
    """
    Main entry point for Brain block tool execution.
    Routes to Modal sandbox in production, local subprocess in dev.
    """
    if _modal_available:
        log.debug("Dispatching %s to Modal sandbox", tool_name)
        return _modal_dispatch(tool_name, tool_input)
    return _dispatch_local(tool_name, tool_input)
