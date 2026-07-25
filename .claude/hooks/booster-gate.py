#!/usr/bin/env python3
"""Agent Booster gate hook — runs smart-read for indexed files, blocking the raw Read."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")
if not file_path:
    sys.exit(0)

# Derive project root from this hook's known location — .claude/hooks/ is 2 levels down
root = Path(__file__).resolve().parent.parent.parent

db_path = root / ".booster" / "symbols.db"
if not db_path.exists():
    sys.exit(0)

try:
    rel = str(Path(file_path).relative_to(root))
except ValueError:
    sys.exit(0)

# Booster developing booster: allow raw Read on booster's own source so edits
# can match exact strings. Smart-read returns symbol slices, not editable content.
if "tools/booster/booster/" in rel or "tools/booster/tests/" in rel:
    sys.exit(0)
# Marketing landing pages: large hand-edited TSX where exact-string Edit needs
# the unmodified content. Smart-read returns symbol slices that don't help.
if "(marketing)" in rel and rel.endswith(".tsx"):
    sys.exit(0)

try:
    conn = sqlite3.connect(str(db_path))
    count = conn.execute("SELECT COUNT(*) FROM symbols WHERE file = ?", (rel,)).fetchone()[0]
    conn.close()
except Exception:
    sys.exit(0)

if count == 0:
    sys.exit(0)  # not indexed — let Read proceed normally

try:
    r = subprocess.run(
        ["booster", "smart-read", rel],
        capture_output=True, text=True, timeout=10, cwd=str(root),
    )
    output = r.stdout.strip()
    if output:
        print(f"[booster/smart-read] intercepted Read → {rel}")
        print(output)
        sys.exit(2)  # block raw Read — smart-read result is the content
except Exception:
    pass

sys.exit(0)  # fallback — let Read proceed if smart-read fails
