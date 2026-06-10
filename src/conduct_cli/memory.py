"""Team session memory helpers for Conduct CLI."""
from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path


def _load_config():
    cfg_path = Path.home() / ".conduct" / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return json.loads(cfg_path.read_text())
    except Exception:
        return None


def post_session_to_api(session_id: str, transcript_path: str | None, repo: str | None) -> bool:
    """Fire-and-forget POST to /team-memory/sessions. Returns True if thread started."""
    cfg = _load_config()
    if not cfg:
        return False
    server = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
    if not server or not workspace_id:
        return False

    raw_transcript = None
    if transcript_path:
        try:
            text = Path(transcript_path).read_text(errors="ignore")
            raw_transcript = text[:12000]
        except Exception:
            pass

    developer_id = cfg.get("user_id") or cfg.get("email") or cfg.get("member_email")
    if not developer_id:
        try:
            import subprocess as _sp
            developer_id = _sp.check_output(
                ["git", "config", "user.email"], stderr=_sp.DEVNULL, text=True
            ).strip() or None
        except Exception:
            pass

    payload = json.dumps({
        "session_id": session_id,
        "tool": "claude_code",
        "repo_full_name": repo,
        "raw_transcript": raw_transcript,
        "files_touched": [],
        "developer_id": developer_id,
    }).encode()

    def _send():
        try:
            req = urllib.request.Request(
                f"{server}/team-memory/sessions",
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": api_key,
                    "X-Workspace-ID": workspace_id,
                },
                method="POST",
            )
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

    t = threading.Thread(target=_send, daemon=True)
    t.start()
    return True


def search_team_memory(query: str, repo: str | None = None, limit: int = 5) -> list[dict]:
    """Search team session memories. Returns list of result dicts, never raises."""
    cfg = _load_config()
    if not cfg:
        return []
    server = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("api_key", "")
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
    if not server or not workspace_id:
        return []

    try:
        import urllib.parse
        params = {"q": query, "limit": str(limit)}
        if repo:
            params["repo"] = repo
        url = f"{server}/team-memory/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(
            url,
            headers={
                "X-API-Key": api_key,
                "X-Workspace-ID": workspace_id,
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
        if isinstance(data, list):
            return data
        return data.get("results", []) if isinstance(data, dict) else []
    except Exception:
        return []
