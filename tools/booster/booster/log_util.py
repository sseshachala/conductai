"""Shared log helper + error interceptor for agent-booster (#718 Phase 1).

Mirror of packages/conduct-cli/src/conduct_cli/log_util.py with PREFIX/TOOL
swapped. Stdlib only, daemon-thread POST, ~/.conductguard/config.json creds
(booster is installed alongside conduct so the same config file is present).

Public API:
    log(level, message, **context)
    install_error_interceptor(main_fn)
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

PREFIX = "[booster]"
TOOL = "agent-booster"

_COLORS = {
    "info":    "\033[37m",
    "ok":      "\033[32m",
    "warning": "\033[33m",
    "error":   "\033[31m",
}
_RESET = "\033[0m"

_API_BASE = os.environ.get("CONDUCT_API_URL", "https://api.conductai.ai").rstrip("/")
_CONFIG   = Path.home() / ".conductguard" / "config.json"
_LOG_FILE = Path(
    os.environ.get("CONDUCT_LOG_FILE")
    or str(Path.home() / ".conductguard" / "logs" / "events.jsonl")
)
_POST_TIMEOUT_S = 2.0

_MAX_BYTES = 10 * 1024 * 1024
_BACKUPS   = 3


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
    """Append one JSONL event to the local log file. Shared with conduct-cli;
    each line carries `tool` so the two streams are distinguishable."""
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
        pass


@lru_cache(maxsize=1)
def _read_creds() -> tuple[str | None, str | None]:
    try:
        cfg = json.loads(_CONFIG.read_text())
        return cfg.get("member_token"), cfg.get("workspace_id")
    except Exception:
        return None, None


@lru_cache(maxsize=1)
def _version() -> str:
    try:
        from importlib.metadata import version
        return version("agent-booster")
    except Exception:
        return "unknown"


def _post_event_sync(event_type: str, message: str, tb: str | None, ctx: dict) -> None:
    token, workspace_id = _read_creds()
    if not token:
        return
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
        pass


def _post_event(event_type: str, message: str, tb: str | None, ctx: dict, *, wait: bool = False) -> None:
    t = threading.Thread(
        target=_post_event_sync,
        args=(event_type, message, tb, ctx),
        daemon=True,
        name="booster-telemetry",
    )
    t.start()
    if wait:
        t.join(timeout=_POST_TIMEOUT_S)


def log(level: str, msg: str, **ctx) -> None:
    color = _COLORS.get(level, "")
    sys.stderr.write(f"{color}{PREFIX} {msg}{_RESET}\n")
    if level in ("warning", "error"):
        _write_local(level, msg, None, ctx)
        _post_event(level, msg, None, ctx)


def install_error_interceptor(main_fn: Callable) -> Callable:
    def wrapped(*args, **kwargs):
        try:
            return main_fn(*args, **kwargs)
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception as e:
            tb = traceback.format_exc()
            msg = f"{type(e).__name__}: {e}"
            _write_local("error", msg, tb, {})
            _post_event("error", msg, tb, {}, wait=True)
            sys.stderr.write(f"{_COLORS['error']}{PREFIX} {msg}{_RESET}\n{tb}\n")
            sys.exit(1)
    wrapped.__wrapped__ = main_fn
    return wrapped
