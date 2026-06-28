"""ConductGuard Stop hook — captures session transcript for team memory."""
from __future__ import annotations

import json
import sys

from conduct_cli.hooks.base import detect_repo


def main() -> None:
    try:
        raw  = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    session_id      = data.get("session_id", "")
    transcript_path = data.get("transcript_path") or data.get("transcriptPath")

    try:
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, detect_repo())
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
