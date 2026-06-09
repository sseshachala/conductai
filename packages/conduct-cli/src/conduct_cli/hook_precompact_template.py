#!/usr/bin/env python3
"""ConductGuard PreCompact hook — persists session context before compaction."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

GUARD_DIR = Path.home() / ".conductguard"
SNAPSHOT_PATH = GUARD_DIR / "session_snapshot.json"


def _git(cmd):
    try:
        return subprocess.check_output(
            ["git"] + cmd, stderr=subprocess.DEVNULL, text=True, timeout=3
        ).strip()
    except Exception:
        return ""


def _guard_status():
    try:
        out = subprocess.check_output(
            ["conductguard", "status", "--json"],
            stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
        return json.loads(out.strip())
    except Exception:
        return None


def _memory_headline():
    try:
        root = Path.cwd()
        mem_key = str(root).replace("/", "-").lstrip("-")
        candidates = [
            Path.home() / ".claude" / "projects" / mem_key / "memory" / "MEMORY.md",
            Path.home() / ".codex" / "projects" / mem_key / "memory" / "MEMORY.md",
        ]
        for mem_path in candidates:
            if mem_path.exists():
                return "\n".join(mem_path.read_text().splitlines()[:10])
    except Exception:
        pass
    return ""


def main():
    try:
        sys.stdin.read()
    except Exception:
        pass

    try:
        GUARD_DIR.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "compacted_at": datetime.now(timezone.utc).isoformat(),
            "tier1": {
                "git_branch": _git(["branch", "--show-current"]),
                "recent_commits": _git(["log", "--oneline", "-3"]),
                "memory_headline": _memory_headline(),
            },
            "tier2": {"guard_status": _guard_status()},
            "tier3": {"cwd": str(Path.cwd()), "python": sys.version.split()[0]},
        }
        tmp = GUARD_DIR / "session_snapshot.tmp"
        tmp.write_text(json.dumps(snapshot, indent=2))
        tmp.rename(SNAPSHOT_PATH)
    except Exception:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
