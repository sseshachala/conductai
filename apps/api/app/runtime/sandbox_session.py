"""
SandboxSession — persistent execution context for a Brain block's agentic loop.

Instead of spinning up a new container/subprocess per tool call, a session is
opened once at the start of the Brain block, all tool calls run inside it, and
it is torn down at the end. This eliminates per-call cold starts and preserves
working directory state across tool calls.

Session lifetime = one Brain block execution.

Backends:
  LocalSession   — tempdir + direct subprocess (dev / no-Modal)
  ModalSession   — one persistent Modal sandbox via exec() per tool call
  RemoteSession  — persistent SSH connection (DigitalOcean / remote host)

Factory:
  create_session(remote_host, credentials) → appropriate session
"""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
import structlog
from typing import Protocol, runtime_checkable

log = structlog.get_logger(__name__)

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


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class SandboxSession(Protocol):
    working_dir: str | None

    def dispatch(self, tool_name: str, tool_input: dict) -> str: ...
    def capture_artifacts(self) -> tuple[list[dict], str]: ...
    def close(self) -> None: ...


# ── Local session ─────────────────────────────────────────────────────────────

class LocalSession:
    """
    Persistent local execution session backed by a temporary directory.
    All tool calls share the same filesystem state across the block's lifetime.
    """

    def __init__(self) -> None:
        self._tmpdir = tempfile.mkdtemp(prefix="conduct_brain_")
        self.working_dir: str | None = self._tmpdir
        log.debug("sandbox_session.local.started", tmpdir=self._tmpdir)

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "read_file":
            return self._read_file(tool_input.get("path", ""))
        if tool_name == "write_file":
            return self._write_file(tool_input.get("path", ""), tool_input.get("content", ""))
        if tool_name == "run_shell":
            return self._run_shell(tool_input.get("command", ""), tool_input.get("working_dir"), tool_input.get("env"))
        if tool_name == "search_code":
            return self._search_code(tool_input.get("pattern", ""), tool_input.get("path", "."), tool_input.get("file_glob", "*"))
        return f"Unknown tool: {tool_name}"

    def _read_file(self, path: str) -> str:
        if not path:
            return "Error: missing required parameter 'path'"
        try:
            with open(path) as f:
                content = f.read()
            return (content[:20_000] + "\n[... truncated]") if len(content) > 20_000 else content
        except Exception as e:
            return f"Error reading file: {e}"

    def _write_file(self, path: str, content: str) -> str:
        if not path:
            return "Error: missing required parameter 'path'"
        try:
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
            return f"Written {len(content)} bytes to {path}"
        except Exception as e:
            return f"Error writing file: {e}"

    def _run_shell(self, command: str, working_dir: str | None = None, env: dict | None = None) -> str:
        if not command:
            return "Error: missing required parameter 'command'"
        for pattern in _FORBIDDEN_SHELL_PATTERNS:
            if re.search(pattern, command):
                return f"Refused: command matches forbidden pattern '{pattern}'"
        # Track working directory across calls
        cwd = working_dir or self.working_dir or self._tmpdir
        if working_dir:
            self.working_dir = working_dir
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

    def _search_code(self, pattern: str, path: str = ".", file_glob: str = "*") -> str:
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

    def capture_artifacts(self) -> tuple[list[dict], str]:
        """Extract git diff evidence from the session working directory."""
        if not self.working_dir:
            return [], ""
        try:
            result = subprocess.run(
                ["git", "diff", "--stat", "HEAD"],
                capture_output=True, text=True, timeout=10, cwd=self.working_dir,
            )
            stat = result.stdout.strip()
            if not stat:
                result = subprocess.run(
                    ["git", "diff", "--stat"],
                    capture_output=True, text=True, timeout=10, cwd=self.working_dir,
                )
                stat = result.stdout.strip()

            files: list[dict] = []
            for line in stat.splitlines():
                m = re.match(r"^\s*(.+?)\s*\|\s*\d+", line)
                if m:
                    fname = m.group(1).strip()
                    if not fname.startswith("..."):
                        files.append({"path": fname, "action": "modified"})
            return files, stat
        except Exception:
            return [], ""

    def close(self) -> None:
        import shutil
        try:
            shutil.rmtree(self._tmpdir, ignore_errors=True)
            log.debug("sandbox_session.local.closed", tmpdir=self._tmpdir)
        except Exception:
            pass


# ── Modal session ─────────────────────────────────────────────────────────────

class ModalSession:
    """
    Persistent Modal sandbox session.
    Creates one sandbox at start; uses exec() for each tool call.
    Significantly cheaper and faster than one sandbox per tool call.
    """

    def __init__(self, token_id: str, token_secret: str) -> None:
        self.working_dir: str | None = None
        self._token_id = token_id
        self._token_secret = token_secret
        self._sandbox = None
        self._started = False

    def _ensure_started(self) -> None:
        if self._started:
            return
        import modal  # type: ignore[import]
        import sys

        proc_env = {**os.environ, "MODAL_TOKEN_ID": self._token_id, "MODAL_TOKEN_SECRET": self._token_secret}
        # Spawn a subprocess that holds the Modal session — credentials stay isolated
        # from the shared API worker env.
        self._session_proc = subprocess.Popen(
            [sys.executable, "-m", "app.runtime.modal_session_runner"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=proc_env,
            text=True,
        )
        self._started = True
        log.debug("sandbox_session.modal.started")

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        """Route to modal_session_runner via stdin/stdout IPC."""
        import json
        try:
            self._ensure_started()
            payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input}) + "\n"
            self._session_proc.stdin.write(payload)
            self._session_proc.stdin.flush()
            response_line = self._session_proc.stdout.readline()
            if not response_line:
                return "Error: Modal session process terminated unexpectedly"
            data = json.loads(response_line)
            if wd := data.get("working_dir"):
                self.working_dir = wd
            return data.get("result", "(no output)")
        except Exception as e:
            log.warning("sandbox_session.modal.dispatch_error", error=str(e))
            # Fall back to local on Modal failure
            local = LocalSession()
            result = local.dispatch(tool_name, tool_input)
            self.working_dir = local.working_dir
            local.close()
            return result

    def capture_artifacts(self) -> tuple[list[dict], str]:
        if not self.working_dir:
            return [], ""
        # Ask the session runner to run git diff
        result = self.dispatch("run_shell", {"command": "git diff --stat HEAD || git diff --stat", "working_dir": self.working_dir})
        files: list[dict] = []
        for line in result.splitlines():
            m = re.match(r"^\s*(.+?)\s*\|\s*\d+", line)
            if m:
                fname = m.group(1).strip()
                if not fname.startswith("..."):
                    files.append({"path": fname, "action": "modified"})
        return files, result

    def close(self) -> None:
        if self._started and self._session_proc:
            try:
                self._session_proc.stdin.write('{"tool_name": "__exit__", "tool_input": {}}\n')
                self._session_proc.stdin.flush()
                self._session_proc.wait(timeout=10)
            except Exception:
                self._session_proc.kill()
            log.debug("sandbox_session.modal.closed")


# ── Remote session ────────────────────────────────────────────────────────────

class RemoteSession:
    """
    Persistent SSH session for remote host execution.
    Reuses one SSH connection across all tool calls in the block.
    """

    def __init__(self, host_config: dict) -> None:
        self.working_dir: str | None = None
        self._host = host_config
        self._client = None

    def _ensure_connected(self):
        if self._client:
            return
        from app.runtime.remote_sandbox import _load_private_key
        import paramiko  # type: ignore[import]

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        pkey = _load_private_key(self._host["private_key"], self._host.get("private_key_passphrase"))
        client.connect(
            hostname=self._host["ip"],
            port=int(self._host.get("port", 22)),
            username=self._host.get("username", "root"),
            pkey=pkey,
            timeout=30,
        )
        self._client = client
        log.debug("sandbox_session.remote.connected", host=self._host["ip"])

    def dispatch(self, tool_name: str, tool_input: dict) -> str:
        from app.runtime.remote_sandbox import remote_dispatch
        # Remote dispatch handles its own connection per call — reuse host config
        if tool_name == "run_shell" and tool_input.get("working_dir"):
            self.working_dir = tool_input["working_dir"]
        return remote_dispatch(tool_name, tool_input, self._host)

    def capture_artifacts(self) -> tuple[list[dict], str]:
        if not self.working_dir:
            return [], ""
        result = self.dispatch("run_shell", {"command": "git diff --stat HEAD || git diff --stat", "working_dir": self.working_dir})
        files: list[dict] = []
        for line in result.splitlines():
            m = re.match(r"^\s*(.+?)\s*\|\s*\d+", line)
            if m:
                fname = m.group(1).strip()
                if not fname.startswith("..."):
                    files.append({"path": fname, "action": "modified"})
        return files, result

    def close(self) -> None:
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        log.debug("sandbox_session.remote.closed", host=self._host.get("ip"))


# ── Factory ───────────────────────────────────────────────────────────────────

def create_session(
    remote_host: dict | None,
    credentials: dict | None,
) -> LocalSession | ModalSession | RemoteSession:
    """
    Return the right session backend for this Brain block execution.

    Priority:
      1. remote_host configured → RemoteSession (SSH)
      2. Modal credentials in workspace env → ModalSession
      3. Local fallback (dev mode) → LocalSession
    """
    if remote_host and remote_host.get("ip"):
        log.debug("sandbox_session.backend", type="remote")
        return RemoteSession(remote_host)

    modal_creds = (credentials or {}).get("modal", {})
    token_id = modal_creds.get("token_id", "")
    token_secret = modal_creds.get("token_secret", "")
    if token_id and token_secret:
        log.debug("sandbox_session.backend", type="modal")
        return ModalSession(token_id, token_secret)

    log.debug("sandbox_session.backend", type="local")
    return LocalSession()
