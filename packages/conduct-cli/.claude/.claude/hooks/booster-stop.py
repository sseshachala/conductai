#!/usr/bin/env python3
"""Booster stop hook — captures actual output tokens from the Claude Code session end event."""
import json
import sys
from pathlib import Path

data = json.load(sys.stdin)

# Claude Code stop event schema: {"session_id": "...", "stop_hook_active": bool, "usage": {...}}
usage = data.get("usage", {})
output_tokens = usage.get("output_tokens") or usage.get("cache_creation_input_tokens")
# Prefer output_tokens; fall back to None if not present
output_tokens_actual = int(output_tokens) if output_tokens is not None else None

root = Path(__file__).resolve().parent.parent.parent  # .claude/hooks/ is 3 levels down

# Read active verbosity mode (if any)
verbosity_file = root / ".booster" / "verbosity.json"
verbosity_mode = "none"
if verbosity_file.exists():
    try:
        v = json.loads(verbosity_file.read_text())
        verbosity_mode = v.get("mode", "none")
    except Exception:
        pass

# Estimate tokens saved if verbosity is active
output_tokens_estimated = None
if verbosity_mode != "none" and output_tokens_actual is not None:
    _RATES = {"lite": 0.30, "full": 0.55, "ultra": 0.75}
    rate = _RATES.get(verbosity_mode, 0.0)
    if rate > 0:
        # estimated = what tokens *would* have been without verbosity reduction
        output_tokens_estimated = int(output_tokens_actual / (1 - rate))

try:
    import sqlite3
    from datetime import datetime, timezone

    db_path = root / ".booster" / "stats.db"
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """INSERT INTO output_sessions
               (ts, platform, verbosity_mode, output_tokens_actual, output_tokens_estimated, is_estimated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).date().isoformat(),
                "claude",
                verbosity_mode,
                output_tokens_actual,
                output_tokens_estimated,
                0 if output_tokens_actual is not None else 1,
            ),
        )
        conn.commit()
        conn.close()
except Exception:
    pass  # never block session teardown

sys.exit(0)
