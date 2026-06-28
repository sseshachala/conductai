"""Shared primitives for all ConductGuard hook modules.

Everything here is stdlib-only so hooks work from a bare `pip install conduct-cli`
with no shell rc sourced.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

# ── Canonical paths ───────────────────────────────────────────────────────────

GUARD_DIR          = Path.home() / ".conductguard"
CONFIG_PATH        = GUARD_DIR / "config.json"
POLICY_PATH        = GUARD_DIR / "policy.json"
BUDGET_CACHE_PATH  = GUARD_DIR / "budget_cache.json"
BUDGET_CACHE_TTL   = 300   # seconds
VERSION_CACHE_PATH = GUARD_DIR / "version_cache.json"
VERSION_CACHE_TTL  = 60    # seconds
WARNED_RULES_PATH  = GUARD_DIR / "warned_rules.json"
SIGNING_KEY_PATH   = GUARD_DIR / "signing.key"
JOURNAL_DIR        = GUARD_DIR / "journal"
JOURNAL_PID_PATH   = JOURNAL_DIR / "drain.pid"

SNAPSHOT_PATH    = GUARD_DIR / "session_snapshot.json"
CONDUCT_ENV_PATH = Path.home() / ".conduct" / "env"

# ── Result type ───────────────────────────────────────────────────────────────

@dataclass
class HookResult:
    action: Literal["allow", "block", "warn"]
    reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ── Config loading ────────────────────────────────────────────────────────────

def load_config() -> dict:
    """Return ~/.conductguard/config.json as a dict; empty dict on any error."""
    try:
        if CONFIG_PATH.exists():
            return json.loads(CONFIG_PATH.read_text())
    except Exception:
        pass
    return {}


# ── Repo / tool detection ─────────────────────────────────────────────────────

def detect_repo() -> Optional[str]:
    """Return 'owner/repo' from git remote origin, or None."""
    try:
        out = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL, text=True,
        ).strip()
        if "github.com" in out:
            return out.split("github.com")[-1].lstrip("/:").rstrip(".git")
    except Exception:
        pass
    return None


def detect_ai_tool() -> str:
    """Return a string identifying the active AI coding tool."""
    import os
    if os.environ.get("CLAUDE_CODE_ENTRYPOINT") or os.environ.get("CLAUDECODE"):
        return "claude-code"
    if os.environ.get("CODEX_SESSION_ID") or os.environ.get("CODEX_CLI_VERSION"):
        return "codex"
    term = os.environ.get("TERM_PROGRAM", "").lower()
    if term == "cursor":
        return "cursor"
    if term == "windsurf":
        return "windsurf"
    path = os.environ.get("PATH", "")
    if "Codex.app" in path or "codex" in path.lower():
        return "codex"
    if "cursor" in path.lower():
        return "cursor"
    if "windsurf" in path.lower():
        return "windsurf"
    return "claude-code"


# ── Journal / drain (fire-and-forget event posting) ───────────────────────────

def journal_append(payload_str: str, api_url: str) -> None:
    """Atomically write one event to the journal for the drain daemon to pick up."""
    try:
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        import random
        name = f"{time.time_ns()}_{random.randint(0, 9999):04d}.json"
        entry = json.dumps({"api_url": api_url, "payload": payload_str})
        tmp = JOURNAL_DIR / (name + ".tmp")
        tmp.write_text(entry)
        tmp.rename(JOURNAL_DIR / name)
    except Exception:
        pass


def ensure_drain_daemon(hook_module_path: Optional[Path] = None) -> None:
    """Start the drain daemon if it is not already running.

    hook_module_path — path of the calling hook file (used to spawn the daemon
    via `python <path> drain`).  When None the drain subprocess is not started
    (used in unit tests / debug mode where the daemon is not needed).
    """
    try:
        if JOURNAL_PID_PATH.exists():
            pid = int(JOURNAL_PID_PATH.read_text().strip())
            import os as _os
            try:
                _os.kill(pid, 0)
                return  # alive
            except (ProcessLookupError, PermissionError):
                pass
        if hook_module_path is None:
            return
        subprocess.Popen(
            [sys.executable, str(hook_module_path), "drain"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception:
        pass


def run_drain_daemon() -> None:
    """Drain the journal directory to the API.  Call via `python hook.py drain`."""
    import os as _os
    try:
        JOURNAL_DIR.mkdir(parents=True, exist_ok=True)
        JOURNAL_PID_PATH.write_text(str(_os.getpid()))
    except Exception:
        return
    empty_scans = 0
    while empty_scans < 3:
        files = sorted(f for f in JOURNAL_DIR.glob("*.json") if f.name != "drain.pid")
        if not files:
            empty_scans += 1
            time.sleep(2)
            continue
        posted_any = False
        for f in files:
            try:
                entry = json.loads(f.read_text())
                api_url = entry["api_url"]
                payload = (
                    entry["payload"].encode()
                    if isinstance(entry["payload"], str)
                    else entry["payload"]
                )
                req = urllib.request.Request(
                    f"{api_url}/guard/events",
                    data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                urllib.request.urlopen(req, timeout=8)
                f.unlink(missing_ok=True)
                posted_any = True
            except Exception:
                pass
        if not posted_any:
            empty_scans += 1
            time.sleep(2)
        else:
            empty_scans = 0
    try:
        JOURNAL_PID_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def post_event(
    tool_name: str,
    tool_input: dict,
    decision: str,
    rule_id: Optional[str] = None,
    message: Optional[str] = None,
    session_id: Optional[str] = None,
    *,
    drain_via: Optional[Path] = None,
) -> None:
    """Post one guard event via the journal/drain pattern.  Never raises.

    drain_via — path of the calling hook file passed to ensure_drain_daemon().
    """
    cfg = load_config()
    workspace_id = cfg.get("workspace_id")
    if not workspace_id:
        return
    import platform as _platform
    _os_info = f"{_platform.system()} {_platform.release()} {_platform.machine()}".strip()
    payload = json.dumps({
        "workspace_id":    workspace_id,
        "clerk_user_id":   cfg.get("user_email"),
        "user_email":      cfg.get("user_email"),
        "ai_tool":         detect_ai_tool(),
        "tool_call":       tool_name,
        "input_summary":   json.dumps(tool_input)[:200],
        "decision":        decision,
        "rule_id":         rule_id,
        "rule_message":    message,
        "hook_session_id": session_id,
        "os_info":         _os_info,
        "hostname":        _platform.node(),
    })
    api_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/")
    journal_append(payload, api_url)
    ensure_drain_daemon(drain_via)
