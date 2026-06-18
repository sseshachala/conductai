#!/usr/bin/env python3
"""Booster grep nudge — runs booster search for semantic patterns, blocking raw Grep."""
import json
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
pattern = data.get("tool_input", {}).get("pattern", "")
if not pattern:
    sys.exit(0)

REGEX_CHARS = set(r"^$*+?[](){}\\|.")
is_regex = any(c in REGEX_CHARS for c in pattern)
word_count = len(pattern.split())

if not is_regex and word_count >= 2:
    root = Path(__file__).resolve().parent.parent.parent
    db_path = root / ".booster" / "symbols.db"
    if not db_path.exists():
        sys.exit(0)  # not indexed — let Grep proceed

    try:
        r = subprocess.run(
            ["booster", "search", pattern],
            capture_output=True, text=True, timeout=10, cwd=str(root),
        )
        output = r.stdout.strip()
        if output:
            print(f"[booster/search] results for {pattern!r}:\n{output}")
            sys.exit(2)  # block Grep — search results are the answer
        else:
            print(f"[booster] No indexed symbols match {pattern!r} — falling through to Grep.")
    except Exception:
        pass

sys.exit(0)
