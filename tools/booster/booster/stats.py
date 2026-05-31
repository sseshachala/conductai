from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_DDL = """
CREATE TABLE IF NOT EXISTS reads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    file TEXT NOT NULL,
    full_tokens INTEGER NOT NULL,
    slice_tokens INTEGER NOT NULL,
    task TEXT NOT NULL DEFAULT ''
)
"""


class StatsTracker:
    def __init__(self, root: Path) -> None:
        db_dir = root / ".booster"
        db_dir.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "stats.db"), check_same_thread=False)
        self._conn.execute(_DDL)
        self._conn.commit()

    def record(self, file: str, full_text: str, slice_text: str, task: str) -> None:
        self._conn.execute(
            "INSERT INTO reads (ts, file, full_tokens, slice_tokens, task) VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).date().isoformat(),
                file,
                len(full_text) // 4,
                len(slice_text) // 4,
                task,
            ),
        )
        self._conn.commit()

    def summary(self) -> dict:
        cur = self._conn.cursor()

        cur.execute("SELECT COUNT(DISTINCT ts) FROM reads")
        sessions: int = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*), SUM(full_tokens), SUM(slice_tokens) FROM reads")
        row = cur.fetchone()
        total_reads: int = row[0] or 0
        full_tokens: int = row[1] or 0
        slice_tokens: int = row[2] or 0
        saved_tokens: int = full_tokens - slice_tokens
        savings_pct: float = round((saved_tokens / full_tokens * 100), 1) if full_tokens else 0.0

        cur.execute(
            """
            SELECT file,
                   SUM(full_tokens - slice_tokens) AS saved,
                   COUNT(*) AS reads
            FROM reads
            GROUP BY file
            ORDER BY saved DESC
            LIMIT 5
            """
        )
        top_files = [{"file": r[0], "saved": r[1], "reads": r[2]} for r in cur.fetchall()]

        return {
            "sessions": sessions,
            "total_reads": total_reads,
            "full_tokens": full_tokens,
            "slice_tokens": slice_tokens,
            "saved_tokens": saved_tokens,
            "savings_pct": savings_pct,
            "top_files": top_files,
        }
