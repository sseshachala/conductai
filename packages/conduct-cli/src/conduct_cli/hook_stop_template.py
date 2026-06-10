#!/usr/bin/env python3
"""ConductGuard Stop hook — captures session transcript for team memory."""
import json
import subprocess
import sys
from pathlib import Path


def _detect_repo():
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


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    session_id = data.get("session_id", "")
    transcript_path = data.get("transcript_path") or data.get("transcriptPath")

    try:
        from conduct_cli.memory import post_session_to_api
        post_session_to_api(session_id, transcript_path, _detect_repo())
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
