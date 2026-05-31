#!/usr/bin/env python3
"""Agent Booster gate hook — redirects Read to smart_read for indexed files."""
import json
import sqlite3
import sys
from pathlib import Path

data = json.load(sys.stdin)
tool_input = data.get("tool_input", {})
file_path = tool_input.get("file_path", "")
if not file_path:
    sys.exit(0)

cwd = Path.cwd()
db_path = cwd / ".booster" / "symbols.db"
if not db_path.exists():
    sys.exit(0)

try:
    rel = str(Path(file_path).relative_to(cwd))
except ValueError:
    sys.exit(0)

try:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM symbols WHERE file = ?", (rel,)).fetchone()[0]
    conn.close()
except Exception:
    sys.exit(0)

if count > 0:
    print(
        f"[booster] '{rel}' has {count} indexed symbols. "
        "Use mcp__agent-booster__smart_read with a task description "
        "to read only the relevant sections and save tokens."
    )
    sys.exit(1)

sys.exit(0)
