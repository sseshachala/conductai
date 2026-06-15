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

from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS, dispatch_tool


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
    def _exec_shell(cmd: str, wd: str, env: dict | None) -> str:
        # cd into working_dir then run; env vars passed via `env K=V` prefix
        return _exec(sandbox, "bash", "-c", f"cd {shlex.quote(wd)} && {cmd}", envs=env or None)

    def _read(path: str) -> str:
        return _exec(sandbox, "bash", "-c", f"cat {shlex.quote(path)} 2>&1")

    def _write(path: str, content: str) -> str:
        # Base64-encode so arbitrary bytes survive shell quoting
        b64 = base64.b64encode(content.encode()).decode()
        script = (
            f"import base64,os; p={path!r}; "
            f"os.makedirs(os.path.dirname(os.path.abspath(p)),exist_ok=True); "
            f"data=base64.b64decode({b64!r}); open(p,'wb').write(data); "
            f"print(f'Written {{len(data)}} bytes to {{p}}')"
        )
        out = _exec(sandbox, "python3", "-c", script)
        return out.strip() or f"Written {len(content)} bytes to {path}"

    return dispatch_tool(tool_name, tool_input, working_dir,
                         exec_shell=_exec_shell, read_file=_read, write_file=_write)


if __name__ == "__main__":
    main()
