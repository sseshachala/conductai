"""Team session memory helpers for Conduct CLI."""
from __future__ import annotations

import json
import sys
import threading
import time
import urllib.request
from pathlib import Path

from conduct_cli.transcript_text import learnings_text, transcript_format

_FLUSH_INTERVAL = 8 * 3600  # 8 hours in seconds
_FLUSH_STAMP = Path.home() / ".conduct" / "last_memory_flush"


def should_periodic_flush() -> bool:
    """True if 8+ hours have passed since the last periodic memory flush."""
    try:
        if not _FLUSH_STAMP.exists():
            return True
        return time.time() - float(_FLUSH_STAMP.read_text(encoding="utf-8").strip()) >= _FLUSH_INTERVAL
    except Exception:
        return True


def mark_flushed() -> None:
    try:
        _FLUSH_STAMP.parent.mkdir(parents=True, exist_ok=True)
        _FLUSH_STAMP.write_text(str(time.time()), encoding="utf-8")
    except Exception:
        pass


def _load_config():
    cfg_path = Path.home() / ".conduct" / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def post_session_to_api(session_id: str, transcript_path: str | None, repo: str | None,
                        tool: str | None = None, *, wait: bool = False) -> bool:
    """POST transcript learnings to /team-memory/sessions, labelled with the real surface.

    No-op (False) for surfaces without a known transcript format, so a Codex or
    Copilot log is never parsed as Claude JSONL or labelled claude_code.
    Fire-and-forget by default; ``wait=True`` sends synchronously (detached workers).
    """
    if tool is None:
        from conduct_cli.hooks.base import detect_ai_tool
        tool = detect_ai_tool()
    fmt = transcript_format(tool)
    if fmt is None:
        return False
    cfg = _load_config()
    if not cfg:
        return False
    server = cfg.get("server", "").rstrip("/")
    api_key = cfg.get("agent_token", "")
    workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
    if not server or not workspace_id:
        return False

    try:
        raw_transcript = learnings_text(fmt, session_id, transcript_path)
    except Exception:
        raw_transcript = None
    if not raw_transcript:
        return False  # The API would store nothing (no_findings) anyway.

    developer_id = cfg.get("user_id") or cfg.get("email") or cfg.get("member_email")

    payload = json.dumps({
        "session_id": session_id,
        "tool": tool,
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

    if wait:
        _send()
        return True
    t = threading.Thread(target=_send, daemon=True)
    t.start()
    return True


def spawn_capture(tool: str, session_id: str, transcript_path: str | None) -> None:
    """Capture in a detached worker so an end-of-session hook returns immediately.

    The hook process exits right after it returns, which would kill a daemon
    thread mid-POST. The worker inherits cwd, so repo detection still works.
    """
    try:
        if transcript_format(tool) is None or not session_id:
            return
        from conduct_cli.hooks.base import spawn_detached
        spawn_detached([sys.executable, "-m", __name__, "capture", tool, session_id, transcript_path or ""])
    except Exception:
        pass


def team_knowledge_lines(limit: int = 3) -> list[str]:
    """Session-start "Team knowledge" block for the current repo; [] when nothing matches."""
    try:
        from conduct_cli.hooks.base import detect_repo
        results = search_team_memory("recent learnings patterns bugs", repo=detect_repo(), limit=limit)
    except Exception:
        return []
    if not results:
        return []
    lines = ["- Team knowledge:"]
    for r in results[:limit]:
        dev = (r.get("developer_id") or "teammate")[:8]
        summary = (r.get("summary") or "")[:120]
        lines.append(f"  {dev}: {summary}")
    return lines


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


def main() -> None:
    """Detached worker: ``python -m conduct_cli.memory capture <tool> <session_id> [path]``."""
    try:
        if len(sys.argv) >= 4 and sys.argv[1] == "capture":
            from conduct_cli.hooks.base import detect_repo
            path = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else None
            post_session_to_api(sys.argv[3], path, detect_repo(), tool=sys.argv[2], wait=True)
    except Exception:
        pass


if __name__ == "__main__":
    main()
