#!/usr/bin/env python3
"""
guard-precompact.py — ConductGuard PreCompact hook
Runs before Claude Code compacts the conversation.
Writes a priority-tiered snapshot to .booster/session_snapshot.json
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def _git(cmd: list[str]) -> str:
    try:
        return subprocess.check_output(["git"] + cmd, capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        return ""


def _guard_status() -> dict | None:
    try:
        out = subprocess.check_output(
            ["conductguard", "status", "--json"],
            capture_output=True, text=True, timeout=3,
        )
        return json.loads(out.strip())
    except Exception:
        return None


def _memory_headline() -> str:
    try:
        root = Path.cwd()
        mem_key = str(root).replace("/", "-").lstrip("-")
        mem_path = Path.home() / ".claude" / "projects" / mem_key / "memory" / "MEMORY.md"
        if mem_path.exists():
            return "\n".join(mem_path.read_text().splitlines()[:10])
    except Exception:
        pass
    return ""


def main() -> None:
    try:
        sys.stdin.read()  # consume stdin (hook payload)
    except Exception:
        pass

    try:
        root = Path.cwd()
        booster_dir = root / ".booster"
        booster_dir.mkdir(exist_ok=True)

        snapshot = {
            "compacted_at": datetime.now(timezone.utc).isoformat(),
            "tier1": {
                "git_branch": _git(["branch", "--show-current"]),
                "recent_commits": _git(["log", "--oneline", "-3"]),
                "memory_headline": _memory_headline(),
            },
            "tier2": {
                "guard_status": _guard_status(),
            },
            "tier3": {
                "cwd": str(root),
                "python": sys.version.split()[0],
            },
        }

        # Atomic write: tmp → rename
        tmp = booster_dir / "session_snapshot.tmp"
        tmp.write_text(json.dumps(snapshot, indent=2))
        tmp.rename(booster_dir / "session_snapshot.json")
    except Exception:
        pass  # never block Claude Code

    sys.exit(0)


if __name__ == "__main__":
    main()
