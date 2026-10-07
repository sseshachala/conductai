"""Shared CLI helpers: terminal colors, config persistence, auth resolution, run streaming."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from conduct_cli import api


RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[32m"
RED    = "\033[31m"
BLUE   = "\033[34m"
GRAY   = "\033[90m"
CYAN   = "\033[36m"
YELLOW = "\033[33m"

CONFIG_PATH  = Path.home() / ".conduct" / "config.json"


# ── Config helpers ────────────────────────────────────────────────────────────

def _load_config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {}


def _save_config(data: dict):
    _atomic_write(CONFIG_PATH, data)


def _resolve(args, key: str, config_key=None):
    """Return value from CLI args first, then config file."""
    val = getattr(args, key.replace("-", "_"), None)
    if val:
        return val
    cfg = _load_config()
    return cfg.get(config_key or key)


def _require_auth(args):
    """Return (server, workspace_id, token) — exit if not configured."""
    cfg        = _load_config()
    server     = _resolve(args, "server") or cfg.get("api_url", "")
    workspace  = _resolve(args, "workspace") or cfg.get("workspace_id") or cfg.get("workspace")
    token      = _resolve(args, "token") or cfg.get("agent_token")

    saved_server = cfg.get("api_url") or cfg.get("server")
    if (server and saved_server and server.rstrip("/") != saved_server.rstrip("/")
            and not getattr(args, "token", None)):
        print("Server differs from the saved login. Log in to that deployment first, "
              "or supply an explicit token and workspace.")
        raise SystemExit(1)

    if not server:
        print(f"{RED}No server set. Run: conduct login{RESET}")
        sys.exit(1)
    if not workspace:
        print(f"{RED}No workspace set. Run: conduct login{RESET}")
        sys.exit(1)
    if not token:
        print(f"{RED}Not authenticated. Run: conduct login{RESET}")
        sys.exit(1)

    return server.rstrip("/"), workspace, token


# ── Stream helper ─────────────────────────────────────────────────────────────

def _stream_run(server: str, workflow_id: str, run_id: str, workspace_id: str, token=None) -> bool:
    hdrs = api.headers(workspace_id, token, "application/json")
    # SSE endpoint reads auth from query params (EventSource can't set headers)
    qs_parts = [f"workspace_id={workspace_id}"]
    if token:
        qs_parts.append(f"token={token}")
    url  = f"{server}/workflows/{workflow_id}/runs/{run_id}/stream?{'&'.join(qs_parts)}"

    def _consume_stream() -> str | None:
        """Consume SSE stream until terminal. Backend keeps stream open across
        pause/resume — run_paused / run_resumed are informational events, not
        stream terminators."""
        for data in api.stream(url, hdrs):
            kind    = data.get("kind", "")
            bid     = data.get("block_id") or ""
            payload = data.get("payload", data)
            prefix  = f"[{bid}] " if bid else ""

            if kind == "block_started":
                label = payload.get("label") or payload.get("type", "")
                print(f"{BLUE}    ▶ {prefix}{label}{RESET}")
            elif kind == "block_completed":
                summary = payload.get("summary") or json.dumps(payload, default=str, ensure_ascii=False)[:120]
                print(f"{GREEN}    ✓ {prefix}{summary}{RESET}")
            elif kind == "block_failed":
                err = payload.get("error", json.dumps(payload, default=str, ensure_ascii=False)[:200])
                print(f"{RED}    ✗ {prefix}{err}{RESET}")
                _tb = (payload.get("failure") or {}).get("traceback")
                if _tb:
                    for _line in str(_tb).rstrip().splitlines():
                        print(f"{RED}      {_line}{RESET}")
            elif kind == "brain_tool_call":
                summary = payload.get("summary", payload.get("tool", ""))
                print(f"      · {summary}{RESET}")
            elif kind == "guard_check":
                n = payload.get("rules_checked", 0)
                block_type = payload.get("block_type", "")
                if payload.get("warnings"):
                    for w in payload["warnings"]:
                        print(f"{YELLOW}    ⚠ [guard:{block_type}] {w.get('rule_id', '')}: {w.get('message', '')}{RESET}")
                elif payload.get("audited"):
                    for a in payload["audited"]:
                        print(f"{BLUE}    ● [guard:{block_type}] {a.get('rule_id', '')}: {a.get('message', '')}{RESET}")
                else:
                    print(f"{GREEN}    ✓ [guard:{block_type}] {n} rules checked — passed{RESET}")
            elif kind == "approval_requested":
                msg = payload.get("message", "")
                url_a = payload.get("approval_url", "")
                print(f"{YELLOW}    ⏸  approval required: {msg}{RESET}")
                if url_a:
                    print(f"{YELLOW}       decide: {url_a}{RESET}")
            elif kind == "run_paused":
                # Backend keeps SSE open across pause/resume. Just show the
                # banner and stay connected — the resume events flow on the
                # same stream.
                print(f"{YELLOW}    ⏸  run paused — waiting for Slack Approve/Reject click...{RESET}")
            elif kind == "run_resumed":
                print(f"{GREEN}    ▶ approval granted — resuming{RESET}")
            elif kind == "run_completed":
                print(f"{BOLD}{GREEN}    ✓ done{RESET}")
                return "completed"
            elif kind == "run_failed":
                err = payload.get("error", "")
                print(f"{BOLD}{RED}    ✗ failed: {err}{RESET}")
                return "failed"
            else:
                print(f"{GRAY}    {kind}: {json.dumps(payload, default=str, ensure_ascii=False)[:120]}{RESET}")
        return None

    outcome = _consume_stream()
    return outcome == "completed"


def _poll_run(server: str, workflow_id: str, run_id: str, hdrs: dict) -> bool:
    """Poll run status until terminal — fallback when SSE stream unavailable.

    'paused' is treated as pass: the run reached a human-approval step, which
    is correct behaviour for approval-gated agents.
    """
    terminal = {"succeeded", "failed", "cancelled"}
    for _ in range(360):  # max 30 min — dependency installs can take 20-25 min
        time.sleep(5)
        try:
            run = api.req("GET", f"{server}/runs/{run_id}", hdrs)
            status = run.get("status", "")
            print(f"{GRAY}    status: {status}{RESET}", end="\r")
            if status == "paused":
                print(f"\n{GRAY}    (paused — awaiting approval){RESET}")
                return True
            if status in terminal:
                print()
                return status == "succeeded"
        except Exception:
            pass
    print(f"{RED}    timed out waiting for run{RESET}")
    return False


def _atomic_write(path: Path, data: dict, *, merge: bool = True) -> None:
    """Write atomically; login replaces credentials instead of retaining stale keys."""
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if merge and path.exists():
        try:
            existing = json.loads(path.read_text())
        except Exception:
            pass
    existing.update(data)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(existing, indent=2))
    os.replace(tmp, path)
    from conduct_cli.hooks.base import restrict_to_owner
    restrict_to_owner(path)
