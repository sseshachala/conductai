"""
Tool engine — pure tool execution helpers used by brain blocks and tool blocks.

Zero dependencies on dag_runner or executor.
"""
from __future__ import annotations

import os
import re
import subprocess
from typing import Any

import structlog

log = structlog.get_logger(__name__)


# ── ref resolution ────────────────────────────────────────────────────────────

def _resolve_refs(value: Any, state: dict) -> Any:
    """Replace {{block_id.field}} references with values from run state."""
    if isinstance(value, str):
        _MISSING = object()

        def replace(m):
            parts = m.group(1).split(".")
            obj = state.get(parts[0], _MISSING)
            if obj is _MISSING:
                log.debug("unresolved_template_ref", ref=m.group(1), top_key=parts[0])
                return m.group(0)
            for p in parts[1:]:
                if isinstance(obj, dict):
                    nxt = obj.get(p, _MISSING)
                    if nxt is _MISSING:
                        log.debug("unresolved_template_ref", ref=m.group(1), missing_key=p)
                        return m.group(0)
                    obj = nxt
            return str(obj)

        return re.sub(r"\{\{([\w.]+)\}\}", replace, value)
    if isinstance(value, dict):
        return {k: _resolve_refs(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(i, state) for i in value]
    return value


# ── subprocess environment sanitisation ──────────────────────────────────────

# Environment variables stripped from the subprocess environment so that
# secrets injected into the worker process cannot be read via `env`, `printenv`,
# or /proc/self/environ by LLM-generated commands.
_SECRET_ENV_VARS = {
    "ANTHROPIC_API_KEY",
    "ENCRYPTION_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_FRONTEND_API",
    "GITHUB_WEBHOOK_SECRET",
    "VERCEL_WEBHOOK_SECRET",
    "SLACK_SIGNING_SECRET",
    "CLI_API_KEY",
    "RESEND_API_KEY",
    "ADMIN_SECRET",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "OPENAI_API_KEY",
    "VOYAGE_API_KEY",
    "SENTRY_DSN",
    "RAILWAY_API_TOKEN",
    "CONDUCT_CRED_TOKEN",
    "CONDUCT_API_URL",
}


def _safe_subprocess_env() -> dict:
    """Return os.environ with all known secret variables stripped out.

    This prevents LLM-generated shell commands from reading process secrets
    via `env`, `printenv`, or `/proc/self/environ`.
    """
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_VARS}


# ── shell command safety ──────────────────────────────────────────────────────

# Commands that are never allowed in run_shell.
# These are last-resort guards — the Brain block runs in Modal sandbox for
# production workloads.  Local execution should still be hardened.
_FORBIDDEN_SHELL_PATTERNS = [
    # Filesystem destruction
    r"rm\s+-[rRfF]*r[rRfF]*\s+/",  # rm -rf / and variants
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/sd",
    r"chmod\s+777\s+/",
    r"chown.*root",
    # Fork bomb
    r":\(\)\{.*\}",
    # Pipe-to-shell (download + execute)
    r"(curl|wget)\s+.*\|\s*(bash|sh|python|perl|ruby|node)",
    # Reverse shell patterns
    r"/dev/tcp/",           # bash -i >& /dev/tcp/HOST/PORT
    r"nc\s+.*-[el]",        # netcat listener/execute mode
    r"socat\s+.*exec",
    # Python/Perl/Ruby one-liners executing arbitrary code
    r"python[23]?\s+-c\s+['\"]?import\s+os",
    r"perl\s+-e\s+.*exec",
    r"ruby\s+-e\s+.*exec",
]


# ── brain tool implementations ────────────────────────────────────────────────

def _tool_read_file(path: str) -> str:
    try:
        with open(path) as f:
            content = f.read()
        if len(content) > 20_000:
            content = content[:20_000] + "\n[... truncated]"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def _tool_write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _tool_run_shell(command: str, working_dir: str | None = None) -> str:
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Refused: command matches forbidden pattern '{pattern}'"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=working_dir,
            env=_safe_subprocess_env(),  # strip secrets from subprocess environment
        )
        output = result.stdout + result.stderr
        if len(output) > 10_000:
            output = output[:10_000] + "\n[... truncated]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60s"
    except Exception as e:
        return f"Error running shell: {e}"


def _tool_search_code(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    try:
        cmd = ["grep", "-r", "--include", file_glob, "-n", pattern, path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout
        if len(output) > 8_000:
            output = output[:8_000] + "\n[... truncated]"
        return output or "(no matches)"
    except Exception as e:
        return f"Error searching: {e}"


def _dispatch_tool(tool_name: str, tool_input: dict, remote_host: dict | None = None, credentials: dict | None = None) -> str:
    from app.runtime.sandbox import dispatch_brain_tool
    return dispatch_brain_tool(tool_name, tool_input, remote_host=remote_host, credentials=credentials)


def _resolve_remote_host(
    block: dict, state: dict, credentials: dict
) -> dict | None:
    """
    If a Brain block declares a remote_host in its config, resolve it into a
    concrete dict suitable for passing to ``dispatch_brain_tool``.

    Block config shape:
        {
            "remote_host": {
                "ip_ref": "{{wait.ip_address}}",           # required
                "credentials_from": "digitalocean",        # integration handle
                "username": "root",                        # optional, default root
                "port": 22                                 # optional, default 22
            }
        }

    The SSH private key is *never* embedded in the workflow JSON — it is read
    from the named integration's encrypted credentials at execution time.
    Returns None when no remote_host is configured (block runs locally / in Modal).
    """
    cfg = block.get("data", {}).get("config", {}) or {}
    rh = cfg.get("remote_host")
    if not rh:
        return None

    ip_ref = rh.get("ip_ref") or rh.get("ip")
    ip = _resolve_refs(ip_ref, state) if isinstance(ip_ref, str) else ip_ref
    if not ip or (isinstance(ip, str) and ip.startswith("{{")):
        # Couldn't resolve — fall back to local execution rather than fail the block.
        log.warning("brain.remote_host_unresolved", block_id=block.get("id"), ip_ref=ip_ref)
        return None

    handle = rh.get("credentials_from") or "digitalocean"
    creds = credentials.get(handle, {}) if isinstance(credentials, dict) else {}
    private_key = creds.get("ssh_private_key") or rh.get("private_key")
    if not private_key:
        log.warning("brain.remote_host_no_key", block_id=block.get("id"), credentials_from=handle)
        return None

    return {
        "ip": ip,
        "username": rh.get("username") or creds.get("ssh_username") or "root",
        "port": int(rh.get("port") or creds.get("ssh_port") or 22),
        "private_key": private_key,
        "private_key_passphrase": creds.get("ssh_private_key_passphrase"),
    }


def _extract_git_evidence(working_dir: str | None) -> tuple[list[dict], str]:
    """Run git diff --stat in working_dir. Returns (files_changed, diff_stat_text)."""
    if not working_dir:
        return [], ""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=working_dir,
        )
        stat = result.stdout.strip()
        if not stat:
            # Nothing committed yet — diff against index
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=10, cwd=working_dir,
            )
            stat = result.stdout.strip()

        files: list[dict] = []
        for line in stat.splitlines():
            line = line.strip()
            if "|" in line:
                path = line.split("|")[0].strip()
                action = "modified"
                if "new file" in line.lower():
                    action = "created"
                elif "deleted" in line.lower():
                    action = "deleted"
                files.append({"path": path, "action": action})
        return files, stat
    except Exception:
        return [], ""


def _summarise_tool_call(tool_name: str, tool_input: dict) -> str:
    """Return a short human-readable description of a single tool call."""
    if tool_name == "run_shell":
        cmd = tool_input.get("command", "")
        wd = tool_input.get("working_dir", "")
        return f"$ {cmd}" + (f"  (in {wd})" if wd else "")
    if tool_name == "write_file":
        return f"write {tool_input.get('path', '')}"
    if tool_name == "read_file":
        return f"read {tool_input.get('path', '')}"
    return tool_name


def _dry_run_mock(integration: str, action: str, params: dict) -> dict:
    """Return a realistic-looking mock result for dry run mode."""
    return {
        "dry_run": True,
        "integration": integration,
        "action": action,
        "params": params,
        "simulated": True,
        "note": f"Dry run — {integration}.{action} would have been called with these params",
    }


_INTEGRATION_HOSTS: dict[str, str] = {
    "github": "api.github.com",
    "slack": "slack.com",
    "linear": "api.linear.app",
    "digitalocean": "api.digitalocean.com",
    "vercel": "api.vercel.com",
    "railway": "backboard.railway.app",
}


def _check_egress(host: str, allowed_hosts: list[str] | None) -> None:
    """Raise PermissionError if host is not in the environment's allowlist."""
    if not allowed_hosts:
        return
    for pattern in allowed_hosts:
        if pattern.startswith("*."):
            if host == pattern[2:] or host.endswith("." + pattern[2:]):
                return
        elif host == pattern:
            return
    raise PermissionError(f"Host {host!r} is not in this environment's allowed_hosts list")
