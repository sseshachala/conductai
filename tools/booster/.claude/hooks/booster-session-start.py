#!/usr/bin/env python3
"""Auto-start booster daemon if not running — fires on every Claude Code session open."""
import subprocess
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent.parent  # .claude/hooks/ is 3 levels down

try:
    result = subprocess.run(
        ["booster", "start"],
        capture_output=True, text=True, timeout=30, cwd=str(root),
    )
    out = result.stdout.strip()
    if out and "already running" not in out.lower():
        print(out)
except Exception:
    pass  # never block the session

sys.exit(0)
