"""
Remote sandbox — executes Brain block tools over SSH on a remote host
(typically an ephemeral DigitalOcean droplet provisioned earlier in the run).

Why this exists: Modal and the local subprocess fallback are fine for code that
runs on infrastructure we own, but customers who want "agent code never touches
your servers" need the work to happen on a host they control. The cleanest
answer is to SSH in from the worker and run the same four tools there.

Public entry point:
    remote_dispatch(tool_name, tool_input, host_config) -> str

``host_config`` shape:
    {
        "ip": "1.2.3.4",
        "username": "root",
        "private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
        "private_key_passphrase": None,   # optional
        "port": 22,                       # optional, default 22
    }

The dispatcher returns a string (matching the local/Modal contract) so the
Brain block can route results back to Claude as a `tool_result`.
"""
from __future__ import annotations

import io
import logging
import re
import shlex
from typing import Any

log = logging.getLogger(__name__)

# Same denylist as the local/Modal paths so behaviour is consistent.
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

DEFAULT_SHELL_TIMEOUT = 120
DEFAULT_READ_TIMEOUT = 30
MAX_SHELL_OUTPUT = 10_000
MAX_FILE_BYTES = 20_000
MAX_GREP_OUTPUT = 8_000


# ── Connection management ────────────────────────────────────────────────────


def _load_private_key(blob: str, passphrase: str | None = None):
    """
    Accept a private key as a PEM/OpenSSH-formatted string and return the
    appropriate paramiko key object. Supports RSA, ECDSA, Ed25519.
    """
    import paramiko  # imported lazily so unit tests can mock cleanly

    text = blob.strip()
    fp = io.StringIO(text)

    # Try each key type in turn. paramiko raises SSHException when the format
    # doesn't match, so we walk the candidates rather than guess from headers
    # (OpenSSH-format keys all share the same BEGIN/END marker).
    candidates = [
        paramiko.Ed25519Key,
        paramiko.ECDSAKey,
        paramiko.RSAKey,
    ]
    last_err: Exception | None = None
    for cls in candidates:
        fp.seek(0)
        try:
            return cls.from_private_key(fp, password=passphrase)
        except paramiko.PasswordRequiredException:
            raise
        except paramiko.SSHException as e:
            last_err = e
            continue

    raise ValueError(f"Could not parse SSH private key: {last_err}")


def _open_client(host_config: dict[str, Any]):
    """Open and return a connected paramiko SSHClient. Caller closes."""
    import paramiko

    ip = host_config.get("ip")
    if not ip:
        raise ValueError("remote host_config missing 'ip'")

    username = host_config.get("username") or "root"
    port = int(host_config.get("port") or 22)
    pkey_blob = host_config.get("private_key")
    if not pkey_blob:
        raise ValueError("remote host_config missing 'private_key'")

    pkey = _load_private_key(pkey_blob, host_config.get("private_key_passphrase"))

    client = paramiko.SSHClient()
    # We accept whatever host key the droplet presents on first connect — these
    # are ephemeral hosts created seconds ago by our own DO integration, so
    # there is no prior trust to verify against. If the customer wants
    # stricter behaviour they can set a known_hosts file via the
    # ``known_hosts`` field; otherwise auto-add is the right default.
    if host_config.get("known_hosts"):
        client.load_host_keys(host_config["known_hosts"])
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    client.connect(
        hostname=ip,
        port=port,
        username=username,
        pkey=pkey,
        timeout=20,
        banner_timeout=20,
        auth_timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    return client


# ── Tool implementations ─────────────────────────────────────────────────────


def _truncate(s: str, limit: int) -> str:
    return s[:limit] + "\n[... truncated]" if len(s) > limit else s


def _remote_read_file(client, path: str) -> str:
    try:
        sftp = client.open_sftp()
        try:
            with sftp.file(path, "r") as f:
                # Cap reads so a giant file can't blow Claude's context window.
                data = f.read(MAX_FILE_BYTES + 1)
        finally:
            sftp.close()
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return _truncate(data, MAX_FILE_BYTES)
    except FileNotFoundError:
        return f"Error reading file: {path} not found"
    except Exception as e:
        return f"Error reading file: {e}"


def _remote_write_file(client, path: str, content: str) -> str:
    try:
        sftp = client.open_sftp()
        try:
            # Ensure parent directory exists. SFTP has no mkdir -p so we walk.
            parent = path.rsplit("/", 1)[0] if "/" in path else ""
            if parent:
                _sftp_makedirs(sftp, parent)
            with sftp.file(path, "w") as f:
                f.write(content)
        finally:
            sftp.close()
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _sftp_makedirs(sftp, path: str) -> None:
    if not path or path == "/":
        return
    parts = [p for p in path.split("/") if p]
    cur = ""
    for part in parts:
        cur = f"{cur}/{part}" if cur or path.startswith("/") else part
        if path.startswith("/") and not cur.startswith("/"):
            cur = "/" + cur
        try:
            sftp.stat(cur)
        except FileNotFoundError:
            sftp.mkdir(cur)


def _remote_run_shell(
    client, command: str, working_dir: str | None = None, timeout: int = DEFAULT_SHELL_TIMEOUT
) -> str:
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command):
            return f"Refused: command matches forbidden pattern '{pattern}'"

    if working_dir:
        # Quote the working dir so spaces / odd chars don't break the cd.
        wrapped = f"cd {shlex.quote(working_dir)} && {command}"
    else:
        wrapped = command

    try:
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=timeout, get_pty=False)
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        combined = out + err
        return _truncate(combined, MAX_SHELL_OUTPUT) or "(no output)"
    except Exception as e:
        return f"Error running shell: {e}"


def _remote_search_code(
    client, pattern: str, path: str = ".", file_glob: str = "*"
) -> str:
    cmd = (
        f"grep -r --include {shlex.quote(file_glob)} -n "
        f"{shlex.quote(pattern)} {shlex.quote(path)}"
    )
    try:
        _, stdout, _ = client.exec_command(cmd, timeout=DEFAULT_READ_TIMEOUT)
        out = stdout.read().decode("utf-8", errors="replace")
        return _truncate(out, MAX_GREP_OUTPUT) or "(no matches)"
    except Exception as e:
        return f"Error searching: {e}"


# ── Public dispatcher ────────────────────────────────────────────────────────


def remote_dispatch(tool_name: str, tool_input: dict, host_config: dict) -> str:
    """
    Run a single Brain tool call on the remote host. Opens a fresh SSH
    connection each time — slightly wasteful but keeps state simple and
    matches how the local/Modal paths work today. If this becomes a hot
    path we can pool clients per (run_id, host) tuple.
    """
    try:
        client = _open_client(host_config)
    except Exception as e:
        log.warning("Remote dispatch failed to connect: %s", e)
        return f"Error connecting to remote host: {e}"

    try:
        if tool_name == "read_file":
            return _remote_read_file(client, tool_input["path"])
        if tool_name == "write_file":
            return _remote_write_file(client, tool_input["path"], tool_input["content"])
        if tool_name == "run_shell":
            return _remote_run_shell(
                client,
                tool_input["command"],
                tool_input.get("working_dir"),
            )
        if tool_name == "search_code":
            return _remote_search_code(
                client,
                tool_input["pattern"],
                tool_input.get("path", "."),
                tool_input.get("file_glob", "*"),
            )
        return f"Unknown tool: {tool_name}"
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001 — best-effort close
            pass


def is_forbidden_command(command: str) -> bool:
    """Public helper so tests / executor can probe the denylist."""
    return any(re.search(p, command) for p in _FORBIDDEN_SHELL_PATTERNS)
