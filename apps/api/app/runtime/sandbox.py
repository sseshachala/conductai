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

# Shared across local and Modal execution paths — single source of truth.
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


def _modal_available() -> bool:
    """Check at call time so .env loading order doesn't matter."""
    from app.core.config import settings
    return bool(settings.modal_token_id and settings.modal_token_secret)


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

# Lazy-initialised Modal function stub — defined once, reused across calls.
_modal_run_tool = None


def _get_modal_run_tool():
    global _modal_run_tool
    if _modal_run_tool is not None:
        return _modal_run_tool

    import modal  # type: ignore[import]

    _app = modal.App("delegator-brain-sandbox-v2")  # bumped to bust Modal image cache
    forbidden_patterns = _FORBIDDEN_SHELL_PATTERNS  # captured at definition time

    _image = (
        modal.Image.debian_slim()
        .apt_install("git", "curl", "wget", "unzip", "python3", "python3-pip", "nodejs", "npm")
        .run_commands("git --version && node --version && python3 --version")  # verify at build time
    )

    @_app.function(timeout=300, cpu=1, memory=1024, retries=0, image=_image)
    def run_tool(name: str, inputs: dict) -> str:
        import os as _os
        import re as _re
        import subprocess as _sp

        if name == "read_file":
            try:
                with open(inputs["path"]) as f:
                    c = f.read()
                return c[:20_000] + "\n[... truncated]" if len(c) > 20_000 else c
            except Exception as e:
                return f"Error: {e}"

        if name == "write_file":
            try:
                _os.makedirs(_os.path.dirname(_os.path.abspath(inputs["path"])), exist_ok=True)
                with open(inputs["path"], "w") as f:
                    f.write(inputs["content"])
                return f"Written {len(inputs['content'])} bytes to {inputs['path']}"
            except Exception as e:
                return f"Error: {e}"

        if name == "run_shell":
            cmd = inputs["command"]
            for p in forbidden_patterns:
                if _re.search(p, cmd):
                    return f"Refused: matches forbidden pattern '{p}'"
            try:
                r = _sp.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=110, cwd=inputs.get("working_dir"),
                )
                out = r.stdout + r.stderr
                return (out[:10_000] + "\n[... truncated]") if len(out) > 10_000 else out or "(no output)"
            except _sp.TimeoutExpired:
                return "Error: timed out"
            except Exception as e:
                return f"Error: {e}"

        if name == "search_code":
            try:
                r = _sp.run(
                    ["grep", "-r", "--include", inputs.get("file_glob", "*"), "-n",
                     inputs["pattern"], inputs.get("path", ".")],
                    capture_output=True, text=True, timeout=15,
                )
                out = r.stdout
                return (out[:8_000] + "\n[... truncated]") if len(out) > 8_000 else out or "(no matches)"
            except Exception as e:
                return f"Error: {e}"

        return f"Unknown tool: {name}"

    _modal_run_tool = run_tool
    return _modal_run_tool


def _modal_dispatch(tool_name: str, tool_input: dict) -> str:
    try:
        fn = _get_modal_run_tool()
        return fn.remote(tool_name, tool_input)
    except Exception as e:
        log.error("Modal dispatch failed, falling back to local: %s", e, exc_info=True)
        return _dispatch_local(tool_name, tool_input)


# ── Public interface ──────────────────────────────────────────────────────────

def _dispatch_local(tool_name: str, tool_input: dict) -> str:
    if tool_name == "read_file":
        if "path" not in tool_input:
            return "Error: missing required parameter 'path'"
        return _local_read_file(tool_input["path"])
    if tool_name == "write_file":
        if "path" not in tool_input:
            return "Error: missing required parameter 'path'"
        if "content" not in tool_input:
            return "Error: missing required parameter 'content'"
        return _local_write_file(tool_input["path"], tool_input["content"])
    if tool_name == "run_shell":
        if "command" not in tool_input:
            return "Error: missing required parameter 'command'"
        return _local_run_shell(tool_input["command"], tool_input.get("working_dir"))
    if tool_name == "search_code":
        if "pattern" not in tool_input:
            return "Error: missing required parameter 'pattern'"
        return _local_search_code(
            tool_input["pattern"],
            tool_input.get("path", "."),
            tool_input.get("file_glob", "*"),
        )
    return f"Unknown tool: {tool_name}"


def dispatch_brain_tool(
    tool_name: str,
    tool_input: dict,
    remote_host: dict | None = None,
) -> str:
    """
    Main entry point for Brain block tool execution.

    Routing precedence:
      1. ``remote_host`` set on the block (e.g. a DO droplet provisioned by an
         earlier tool block in the same run) -> run over SSH on that host.
      2. Modal sandbox configured -> ephemeral container.
      3. Local subprocess -> dev fallback.
    """
    if remote_host and remote_host.get("ip"):
        from app.runtime.remote_sandbox import remote_dispatch

        log.debug("Dispatching %s to remote host %s", tool_name, remote_host.get("ip"))
        return remote_dispatch(tool_name, tool_input, remote_host)

    if _modal_available():
        log.debug("Dispatching %s to Modal sandbox", tool_name)
        return _modal_dispatch(tool_name, tool_input)
    return _dispatch_local(tool_name, tool_input)
