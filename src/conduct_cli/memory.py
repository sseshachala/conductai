"""Team session memory helpers for Conduct CLI."""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

_FLUSH_INTERVAL = 8 * 3600  # 8 hours in seconds
_FLUSH_STAMP = Path.home() / ".conduct" / "last_memory_flush"


def should_periodic_flush() -> bool:
    """True if 8+ hours have passed since the last periodic memory flush."""
    try:
        if not _FLUSH_STAMP.exists():
            return True
        return time.time() - float(_FLUSH_STAMP.read_text().strip()) >= _FLUSH_INTERVAL
    except Exception:
        return True


def mark_flushed() -> None:
    try:
        _FLUSH_STAMP.parent.mkdir(parents=True, exist_ok=True)
        _FLUSH_STAMP.write_text(str(time.time()))
    except Exception:
        pass


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
    api_key = cfg.get("agent_token", "")
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
    if not server or not workspace_id:
        return False

    raw_transcript = None
    if transcript_path:
        try:
            lines = Path(transcript_path).read_text(errors="ignore").splitlines()
            msgs = []
            for line in lines:
                try:
                    d = json.loads(line)
                    msg = d.get("message", {})
                    if isinstance(msg, dict) and msg.get("role") in ("user", "assistant"):
                        content = msg.get("content", "")
                        if isinstance(content, list):
                            for c in content:
                                if isinstance(c, dict) and c.get("type") == "text" and c.get("text", "").strip():
                                    msgs.append(f"{msg['role']}: {c['text'][:500]}")
                        elif isinstance(content, str) and content.strip():
                            msgs.append(f"{msg['role']}: {content[:500]}")
                except Exception:
                    pass
            if msgs:
                # Take last 60 messages — end of session has the actual decisions/fixes
                tail = msgs[-60:]
                raw_transcript = "\n\n".join(tail)[:12000]
            else:
                raw_transcript = None
        except Exception:
            pass

    developer_id = cfg.get("user_id") or cfg.get("email") or cfg.get("member_email")

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
                    "Authorization": f"Bearer {api_key}",
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
    api_key = cfg.get("agent_token", "")
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
                "Authorization": f"Bearer {api_key}",
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
