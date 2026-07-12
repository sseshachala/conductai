"""Shared log helper + error interceptor for conduct-cli (#718 Phase 1).

Stdlib only. No new dependencies. Failures here MUST NEVER block the user —
telemetry is best-effort. The POST runs in a daemon thread with a join
timeout so even a hung endpoint can't delay CLI exit by more than ~2s.

Public API:
    log(level, message, **context)       # print + (warn/err) post
    install_error_interceptor(main_fn)   # wrap top-level entry point
"""
from __future__ import annotations

import json
import os
import sys
import threading
import traceback
import urllib.request
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable

PREFIX = "[conduct]"
TOOL = "conduct-cli"

_COLORS = {
    "info":    "\033[37m",
    "ok":      "\033[32m",
    "warning": "\033[33m",
    "error":   "\033[31m",
}
_RESET = "\033[0m"

_API_BASE = os.environ.get("CONDUCT_API_URL", "https://api.conductai.ai").rstrip("/")
_CONFIG   = Path.home() / ".conduct" / "config.json"
_LOG_FILE = Path(
    os.environ.get("CONDUCT_LOG_FILE")
    or str(Path.home() / ".conduct" / "logs" / "events.jsonl")
)
_POST_TIMEOUT_S = 2.0

_MAX_BYTES = 10 * 1024 * 1024   # 10MB
_BACKUPS   = 3                  # keep events.jsonl.1, .2, .3


def _rotate() -> None:
    """events.jsonl → .1 → .2 → .3; oldest dropped. Silent on failure."""
    base = str(_LOG_FILE)
    try:
        oldest = Path(f"{base}.{_BACKUPS}")
        if oldest.exists():
            oldest.unlink()
        for i in range(_BACKUPS - 1, 0, -1):
            src = Path(f"{base}.{i}")
            if src.exists():
                src.replace(Path(f"{base}.{i + 1}"))
        if _LOG_FILE.exists():
            _LOG_FILE.replace(Path(f"{base}.1"))
    except Exception:
        pass


def _write_local(event_type: str, message: str, tb: str | None, ctx: dict) -> None:
    """Append one JSONL event to the local log file. Foreground, fast, silent on failure."""
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size >= _MAX_BYTES:
            _rotate()
        line = json.dumps({
            "ts":         datetime.now(timezone.utc).isoformat(),
            "tool":       TOOL,
            "version":    _version(),
            "event_type": event_type,
            "message":    message,
            "traceback":  tb,
            "run_id":     os.environ.get("CONDUCT_RUN_ID"),
            "session_id": os.environ.get("CONDUCT_SESSION_ID"),
            "context":    ctx or {},
        })
        with _LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # disk failure must never block the user


@lru_cache(maxsize=1)
def _read_creds() -> tuple[str | None, str | None]:
    """(member_token, workspace_id) from ~/.conduct/config.json, or (None, None)."""
    try:
        cfg = json.loads(_CONFIG.read_text())
        return cfg.get("member_token"), cfg.get("workspace_id")
    except Exception:
        return None, None


@lru_cache(maxsize=1)
def _version() -> str:
    try:
        from importlib.metadata import version
        return version("conduct-cli")
    except Exception:
        return "unknown"


def _post_event_sync(event_type: str, message: str, tb: str | None, ctx: dict) -> None:
    token, workspace_id = _read_creds()
    if not token:
        return  # no creds = no telemetry, silent
    body = json.dumps({
        "tool":       TOOL,
        "version":    _version(),
        "event_type": event_type,
        "message":    message[:4000],
        "traceback":  tb,
        "run_id":     os.environ.get("CONDUCT_RUN_ID"),
        "session_id": os.environ.get("CONDUCT_SESSION_ID"),
        "context":    ctx or {},
    }).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type":  "application/json",
    }
    if workspace_id:
        headers["X-Workspace-Id"] = workspace_id
    try:
        req = urllib.request.Request(
            f"{_API_BASE}/telemetry/events",
            data=body,
            headers=headers,
            method="POST",
        )
        urllib.request.urlopen(req, timeout=_POST_TIMEOUT_S)
    except Exception:
        pass  # ponytail: silent — telemetry must never block the user


def _post_event(event_type: str, message: str, tb: str | None, ctx: dict, *, wait: bool = False) -> None:
    """Fire-and-forget by default; wait=True for the error interceptor so the
    POST has a chance to land before sys.exit."""
    t = threading.Thread(
        target=_post_event_sync,
        args=(event_type, message, tb, ctx),
        daemon=True,
        name="conduct-telemetry",
    )
    t.start()
    if wait:
        t.join(timeout=_POST_TIMEOUT_S)


def log(level: str, msg: str, **ctx) -> None:
    """Print to stderr with a colored prefix; warn/error also persist locally
    AND post to telemetry. Same event, three destinations, written once each."""
    color = _COLORS.get(level, "")
    sys.stderr.write(f"{color}{PREFIX} {msg}{_RESET}\n")
    if level in ("warning", "error"):
        _write_local(level, msg, None, ctx)  # foreground, always
        _post_event(level, msg, None, ctx)   # background, best-effort


def install_error_interceptor(main_fn: Callable) -> Callable:
    """Wrap a CLI entry point. Unhandled exception → telemetry POST → stderr → exit 1.

    SystemExit / KeyboardInterrupt pass through unchanged.
    """
    def wrapped(*args, **kwargs):
        try:
            return main_fn(*args, **kwargs)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            tb = traceback.format_exc()
            msg = f"{type(e).__name__}: {e}"
            _write_local("error", msg, tb, {})   # foreground, ensures file row before exit
            _post_event("error", msg, tb, {}, wait=True)  # background, best-effort
            sys.stderr.write(f"{_COLORS['error']}{PREFIX} {msg}{_RESET}\n{tb}\n")
            sys.exit(1)
    wrapped.__wrapped__ = main_fn
    return wrapped
