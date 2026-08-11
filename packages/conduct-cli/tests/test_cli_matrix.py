"""CLI command matrix — Phase 2 of the test-harness plan.

Recursively discovers every `conduct` subcommand from `--help` output and
parametrises three checks per command:

  A. `--help` exits 0                       (import/parser wiring intact)
  B. No arguments exits non-zero            (no command silently does nothing)
  C. When it hits the API, it hits the URL  (auth boundary — CONDUCT_SERVER
     override reaches a local 401 mock; assert we saw traffic OR the command
     is on the OFFLINE_ONLY list)

Every rung is auto-generated from the CLI itself — new subcommand added?
Test picks it up. No hardcoded command list to drift.
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

CONDUCT = shutil.which("conduct") or "conduct"

# Commands that intentionally do NOT touch the API (local ops only).
# Kept small on purpose — add sparingly, with a comment.
OFFLINE_ONLY: set[tuple[str, ...]] = {
    ("login",),               # opens browser, no direct API from CLI process
    ("mcp", "install"),       # writes local Claude/Codex config
    ("session-report",),      # scans local files
    ("test-guard",),          # local synthetic events
    ("test-security",),       # local synthetic findings
}

# Match `{a,b,c}` in the argparse "positional arguments:" section only.
# Option choices like `--flag {yes,no}` and unrelated braces in help text
# are ignored — that block is where argparse renders subparser groups.
POSITIONAL_BLOCK_RE = re.compile(
    r"positional arguments:\s*\n\s*\{([^\{\}]+)\}",
    re.MULTILINE,
)


# ── Discovery ────────────────────────────────────────────────────────────────
def _help(path: tuple[str, ...]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [CONDUCT, *path, "--help"],
        capture_output=True, text=True, timeout=15,
    )


def _subcommands_of(path: tuple[str, ...]) -> list[str]:
    r = _help(path)
    if r.returncode != 0:
        return []
    m = POSITIONAL_BLOCK_RE.search(r.stdout)
    if not m:
        return []
    return [s.strip() for s in m.group(1).split(",") if s.strip()]


def _walk(path: tuple[str, ...] = (), depth: int = 0, parent_children=()) -> list[tuple[str, ...]]:
    # Depth cap: real tree is at most 3 deep (e.g. `guard session start`).
    if depth > 3:
        return []
    out = [path] if path else []
    children = _subcommands_of(path)
    # `debug-hook <hook>` shows the same choice-list as `debug-hook` — argparse
    # renders positional choices identically to subparser groups. Detect and stop.
    if tuple(children) == parent_children:
        return out
    for child in children:
        out.extend(_walk(path + (child,), depth + 1, tuple(children)))
    return out


try:
    ALL_COMMANDS: list[tuple[str, ...]] = [p for p in _walk() if p]
except (FileNotFoundError, subprocess.SubprocessError):
    ALL_COMMANDS = []


# ── Mock server ──────────────────────────────────────────────────────────────
class _Recorder(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self): self._respond()
    def do_POST(self): self._respond()
    def do_PUT(self): self._respond()
    def do_DELETE(self): self._respond()
    def do_PATCH(self): self._respond()

    def _respond(self):
        _Recorder.hits.append(f"{self.command} {self.path}")
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"detail": "mock 401"}')

    def log_message(self, *_):  # keep test output clean
        pass


@pytest.fixture(scope="module")
def mock_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), _Recorder)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ── Tests ────────────────────────────────────────────────────────────────────
def test_cli_installed():
    assert CONDUCT and Path(CONDUCT).exists(), (
        "`conduct` binary not on PATH — install with `pip install -e packages/conduct-cli`"
    )


def test_commands_discovered():
    assert ALL_COMMANDS, "No subcommands discovered — CLI parser or --help broken"


@pytest.mark.parametrize("cmd", ALL_COMMANDS, ids=[" ".join(c) for c in ALL_COMMANDS])
def test_help_succeeds(cmd):
    """Every command / subcommand must respond to --help with exit 0."""
    r = _help(cmd)
    assert r.returncode == 0, (
        f'conduct {" ".join(cmd)} --help exited {r.returncode}\n'
        f'stdout: {r.stdout[-400:]}\nstderr: {r.stderr[-400:]}'
    )


def _leaf_commands() -> list[tuple[str, ...]]:
    """Only commands with NO sub-subcommands (actual invokable actions)."""
    return [c for c in ALL_COMMANDS if not _subcommands_of(c)]


LEAVES = _leaf_commands()


@pytest.mark.matrix
@pytest.mark.parametrize("cmd", LEAVES, ids=[" ".join(c) for c in LEAVES])
def test_auth_boundary(cmd, mock_server, tmp_path, monkeypatch):
    """No leaf command should complete cleanly against an unauthenticated
    server. Either it hits the mock (proves it tried to auth) or it's on
    OFFLINE_ONLY (proves we know it's local-only)."""
    if cmd in OFFLINE_ONLY:
        pytest.skip(f"{' '.join(cmd)} is documented as offline-only")

    _Recorder.hits.clear()
    env = os.environ.copy()
    env.update({
        "CONDUCT_SERVER": mock_server,
        "HOME": str(tmp_path),                  # isolate ~/.conduct/config.json
        "USERPROFILE": str(tmp_path),           # Windows equivalent
        "CONDUCT_NON_INTERACTIVE": "1",
        "NO_COLOR": "1",
    })
    r = subprocess.run(
        [CONDUCT, *cmd],
        capture_output=True, text=True, timeout=20, env=env,
    )
    hit_server = bool(_Recorder.hits)
    exited_nonzero = r.returncode != 0

    assert hit_server or exited_nonzero, (
        f'conduct {" ".join(cmd)} exited 0 without touching the API — '
        f'either it needs auth (bug) or add it to OFFLINE_ONLY.\n'
        f'stdout: {r.stdout[-400:]}\nstderr: {r.stderr[-400:]}'
    )
