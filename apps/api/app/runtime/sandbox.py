"""
Isolated execution sandbox for Brain block tool calls.

Modal credentials must come from the workspace environment (Settings →
Environments → MODAL_TOKEN_ID / MODAL_TOKEN_SECRET). There is no
platform-level Modal fallback.

When Modal credentials are present, each Brain block tool call is dispatched
into an ephemeral Modal container via a short-lived subprocess — credentials
exist only for that subprocess's lifetime and never touch the shared API
worker process env (Centaur-inspired isolation pattern).

When Modal credentials are absent, falls back to direct local subprocess
execution (dev mode only).
"""
import os
import re
import structlog
import subprocess

log = structlog.get_logger(__name__)

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
    """Legacy check — used only by /health/sandbox. Always False now that
    platform-level Modal credentials are removed (see #202)."""
    return False


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


def _local_run_shell(command: str, working_dir: str | None = None, env: dict | None = None) -> str:
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command):
            return f"Refused: command matches forbidden pattern '{pattern}'"
    try:
        import os as _os
        merged_env = {**_os.environ, **(env or {})}
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120,
            cwd=working_dir, env=merged_env,
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
# Uses modal.Sandbox for ephemeral container execution — no pre-deployment needed.

_SANDBOX_SCRIPT = r"""
import json, os, re, subprocess, sys

name   = os.environ["TOOL_NAME"]
inputs = json.loads(os.environ["TOOL_INPUT"])

_forbidden = [
    r"rm\s+-rf\s+/", r"rm\s+-fr\s+/", r"mkfs", r"dd\s+if=",
    r":\(\)\{.*\}", r">\s*/dev/sd", r"chmod\s+777\s+/", r"chown.*root",
]

if name == "read_file":
    try:
        with open(inputs["path"]) as f:
            c = f.read()
        print(c[:20000] + "\n[... truncated]" if len(c) > 20000 else c, end="")
    except Exception as e:
        print(f"Error: {e}", end="")

elif name == "write_file":
    try:
        os.makedirs(os.path.dirname(os.path.abspath(inputs["path"])), exist_ok=True)
        with open(inputs["path"], "w") as f:
            f.write(inputs["content"])
        print(f"Written {len(inputs['content'])} bytes to {inputs['path']}", end="")
    except Exception as e:
        print(f"Error: {e}", end="")

elif name == "run_shell":
    cmd = inputs["command"]
    for p in _forbidden:
        if re.search(p, cmd):
            print(f"Refused: matches forbidden pattern '{p}'", end="")
            sys.exit(0)
    try:
        merged_env = {**os.environ, **(inputs.get("env") or {})}
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=110, cwd=inputs.get("working_dir"), env=merged_env,
        )
        out = r.stdout + r.stderr
        print((out[:10000] + "\n[... truncated]") if len(out) > 10000 else out or "(no output)", end="")
    except subprocess.TimeoutExpired:
        print("Error: timed out", end="")
    except Exception as e:
        print(f"Error: {e}", end="")

elif name == "search_code":
    try:
        r = subprocess.run(
            ["grep", "-r", "--include", inputs.get("file_glob", "*"), "-n",
             inputs["pattern"], inputs.get("path", ".")],
            capture_output=True, text=True, timeout=15,
        )
        out = r.stdout
        print((out[:8000] + "\n[... truncated]") if len(out) > 8000 else out or "(no matches)", end="")
    except Exception as e:
        print(f"Error: {e}", end="")

else:
    print(f"Unknown tool: {name}", end="")
"""


def _modal_dispatch(tool_name: str, tool_input: dict) -> str:
    import json
    import modal  # type: ignore[import]

    app = modal.App.lookup("conduct-sandbox", create_if_missing=True)
    image = (
        modal.Image.debian_slim()
        .apt_install("git", "curl", "wget", "unzip", "python3", "python3-pip", "nodejs", "npm")
    )

    sb = modal.Sandbox.create(
        "python3", "-c", _SANDBOX_SCRIPT,
        app=app,
        image=image,
        timeout=300,
        env={
            "TOOL_NAME": tool_name,
            "TOOL_INPUT": json.dumps(tool_input),
        },
    )
    try:
        result = sb.stdout.read()
        stderr = sb.stderr.read()
        sb.wait()
        return result or stderr or "(no output)"
    except Exception as e:
        error_type = type(e).__name__
        msg = f"[Modal error — {error_type}] {e}"
        log.error("modal.dispatch_error", tool_name=tool_name, error=str(e), exc_info=True)
        raise RuntimeError(msg) from e
    finally:
        try:
            sb.terminate()
        except Exception:
            pass


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
        return _local_run_shell(tool_input["command"], tool_input.get("working_dir"), tool_input.get("env"))
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
    credentials: dict | None = None,
) -> str:
    """
    Main entry point for Brain block tool execution.

    Routing precedence:
      1. remote_host set on the block → SSH dispatch to that host.
      2. Modal credentials in workspace environment → ephemeral Modal container
         via isolated subprocess (credentials never touch shared API worker env).
      3. Local subprocess → dev fallback (no Modal configured).
    """
    if remote_host and remote_host.get("ip"):
        from app.runtime.remote_sandbox import remote_dispatch
        log.debug("sandbox.dispatch", tool=tool_name, backend="remote", host=remote_host.get("ip"))
        return remote_dispatch(tool_name, tool_input, remote_host)

    modal_creds = (credentials or {}).get("modal", {})
    _env_vars = (credentials or {}).get("env_vars") or {}
    token_id = modal_creds.get("token_id") or _env_vars.get("modal_token_id") or _env_vars.get("MODAL_TOKEN_ID") or ""
    token_secret = modal_creds.get("token_secret") or _env_vars.get("modal_token_secret") or _env_vars.get("MODAL_TOKEN_SECRET") or ""

    if token_id and token_secret:
        import json
        import sys
        payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
        log.debug("sandbox.dispatch", tool=tool_name, backend="modal_subprocess")
        proc = subprocess.run(
            [sys.executable, "-m", "app.runtime.modal_runner", payload],
            env={**os.environ, "MODAL_TOKEN_ID": token_id, "MODAL_TOKEN_SECRET": token_secret},
            capture_output=True,
            text=True,
            timeout=360,
        )
        if proc.returncode != 0:
            err = proc.stderr[:500] or "unknown error"
            log.error("sandbox.modal_subprocess_failed", tool=tool_name, error=err)
            raise RuntimeError(f"Modal sandbox failed: {err}")
        return proc.stdout

    log.debug("sandbox.dispatch", tool=tool_name, backend="local")
    return _dispatch_local(tool_name, tool_input)
