"""ConductGuard Stop hook — captures session transcript for team memory and parses intent."""
from __future__ import annotations

import json
import sys

from conduct_cli.hooks.base import detect_repo


def _post_intent(session_id: str, ai_tool: str, cwd: str | None) -> None:
    """Parse session file and PATCH intent to the API. Never raises."""
    try:
        from conduct_cli.hooks.session_parser import parse_session
        data = parse_session(ai_tool, session_id, cwd)
    except Exception:
        print("Guard: session parse failed", file=sys.stderr)
        return

    try:
        import json as _json
        import urllib.request
        from pathlib import Path

        cfg_path = Path.home() / ".conduct" / "config.json"
        if not cfg_path.exists():
            return
        cfg = _json.loads(cfg_path.read_text())
        server = cfg.get("server", "").rstrip("/")
        api_key = cfg.get("api_key", "")
        workspace_id = cfg.get("workspace_id") or cfg.get("workspace", "")
        if not server or not session_id:
            return

        payload = _json.dumps({
            "intent": data.intent,
            "tool_sequence": data.tool_sequence,
            "session_parse_status": data.status,
            "session_parser": data.parser,
        }).encode()

        req = urllib.request.Request(
            f"{server}/guard/sessions/{session_id}/intent",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key,
                "X-Workspace-ID": workspace_id,
            },
            method="PATCH",
        )
        urllib.request.urlopen(req, timeout=8)

        if data.status in ("ok", "partial"):
            print("Guard: session intent captured", file=sys.stderr)
        else:
            print(f"Guard: session parse {data.status}", file=sys.stderr)
    except Exception:
        print("Guard: session parse failed", file=sys.stderr)


def _spawn_session_report(session_id: str) -> None:
    """Fire paxel analysis + Guard push in a detached subprocess. Never blocks."""
    try:
        import subprocess
        subprocess.Popen(
            [sys.executable, "-m", "conduct_cli.hooks.session_report_push", session_id],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass


def main() -> None:
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    session_id      = data.get("session_id", "")
    transcript_path = data.get("transcript_path") or data.get("transcriptPath")
    ai_tool         = data.get("tool", "claude_code")
    cwd             = data.get("cwd")

    try:
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, detect_repo())
    except Exception:
        pass

    try:
        _post_intent(session_id, ai_tool, cwd)
    except Exception:
        pass

    # Fire paxel analysis in background — non-blocking, posts to /guard/session-reports
    _spawn_session_report(session_id)

    sys.exit(0)


if __name__ == "__main__":
    main()
