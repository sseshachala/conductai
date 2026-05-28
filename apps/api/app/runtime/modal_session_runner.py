"""
modal_session_runner — persistent Modal sandbox IPC subprocess.

ModalSession spawns one instance of this process per Brain block. Modal
credentials are in this process's env only — never in the API worker env.

Creates ONE Modal sandbox at startup, then handles tool calls via sandbox.exec()
so the sandbox filesystem persists across tool calls within the same block.

Communication: JSON lines over stdin/stdout.
  stdin:  {"tool_name": "run_shell", "tool_input": {...}}
  stdout: {"result": "...", "working_dir": "/tmp/..."}
  exit:   {"tool_name": "__exit__"}
"""
from __future__ import annotations

import base64
import json
import re
import shlex
import sys

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


def _exec(sandbox, *args: str, envs: dict | None = None) -> str:
    # Pass env vars as separate leading args to `env` so they never appear
    # in the bash -c script string and won't be logged by Modal.
    if envs:
        args = ("env", *[f"{k}={v}" for k, v in envs.items()], *args)
    proc = sandbox.exec(*args)
    out = proc.stdout.read()
    err = proc.stderr.read()
    proc.wait()
    if isinstance(out, bytes):
        out = out.decode("utf-8", errors="replace")
    if isinstance(err, bytes):
        err = err.decode("utf-8", errors="replace")
    return out + err


def main() -> None:
    import modal  # type: ignore[import]

    app = modal.App.lookup("conduct-sandbox", create_if_missing=True)
    image = (
        modal.Image.debian_slim()
        .apt_install("git", "curl", "wget", "unzip", "python3", "python3-pip", "nodejs", "npm")
    )
    # "sleep infinity" keeps the sandbox alive so exec() calls can run into it.
    # Without an entrypoint the sandbox exits immediately and exec() has nothing to attach to.
    sandbox = modal.Sandbox.create("sleep", "infinity", app=app, image=image, timeout=3600)
    working_dir = "/tmp"

    # Write sandbox ID as the first stdout line so ModalSession can terminate
    # the sandbox directly from the API process if the subprocess is force-killed.
    sys.stdout.write(json.dumps({"sandbox_id": sandbox.object_id}) + "\n")
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
            result = _dispatch(sandbox, tool_name, tool_input, working_dir)

            # working_dir is mutable across calls — track it here
            if tool_name == "run_shell" and tool_input.get("working_dir"):
                working_dir = tool_input["working_dir"]

            sys.stdout.write(json.dumps({"result": result, "working_dir": working_dir}) + "\n")
            sys.stdout.flush()
    finally:
        try:
            sandbox.terminate()
        except Exception:
            pass


def _dispatch(sandbox, tool_name: str, tool_input: dict, working_dir: str) -> str:
    if tool_name == "read_file":
        path = tool_input.get("path", "")
        if not path:
            return "Error: missing required parameter 'path'"
        out = _exec(sandbox, "bash", "-c", f"cat {shlex.quote(path)} 2>&1")
        return (out[:20_000] + "\n[... truncated]") if len(out) > 20_000 else out

    if tool_name == "write_file":
        path = tool_input.get("path", "")
        content = tool_input.get("content", "")
        if not path:
            return "Error: missing required parameter 'path'"
        # Base64-encode content so arbitrary bytes survive shell quoting
        b64 = base64.b64encode(content.encode()).decode()
        script = (
            f"import base64,os; p={path!r}; "
            f"os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True); "
            f"data=base64.b64decode({b64!r}); open(p,'wb').write(data); "
            f"print(f'Written {{len(data)}} bytes to {{p}}')"
        )
        out = _exec(sandbox, "python3", "-c", script)
        return out.strip() or f"Written {len(content)} bytes to {path}"

    if tool_name == "run_shell":
        command = tool_input.get("command", "")
        if not command:
            return "Error: missing required parameter 'command'"
        for pattern in _FORBIDDEN_SHELL_PATTERNS:
            if re.search(pattern, command):
                return f"Refused: command matches forbidden pattern '{pattern}'"
        wd = tool_input.get("working_dir") or working_dir
        env = tool_input.get("env") or {}
        full_cmd = f"cd {shlex.quote(wd)} && {command}"
        # Pass env vars via `env KEY=value bash -c '...'` — keeps tokens out of the script string.
        out = _exec(sandbox, "bash", "-c", full_cmd, envs=env or None)
        return (out[:10_000] + "\n[... truncated]") if len(out) > 10_000 else out or "(no output)"

    if tool_name == "search_code":
        pattern = tool_input.get("pattern", "")
        if not pattern:
            return "Error: missing required parameter 'pattern'"
        path = tool_input.get("path", ".")
        file_glob = tool_input.get("file_glob", "*")
        cmd = f"grep -r --include={shlex.quote(file_glob)} -n {shlex.quote(pattern)} {shlex.quote(path)}"
        out = _exec(sandbox, "bash", "-c", cmd)
        return (out[:8_000] + "\n[... truncated]") if len(out) > 8_000 else out or "(no matches)"

    return f"Unknown tool: {tool_name}"


if __name__ == "__main__":
    main()
