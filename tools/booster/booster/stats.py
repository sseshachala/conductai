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
);
CREATE TABLE IF NOT EXISTS output_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'claude',
    verbosity_mode TEXT NOT NULL,
    output_tokens_actual INTEGER,
    output_tokens_estimated INTEGER,
    is_estimated INTEGER NOT NULL DEFAULT 1
)
"""

_VERBOSITY_SAVINGS_RATE = {
    "lite": 0.30,
    "full": 0.55,
    "ultra": 0.75,
}


class StatsTracker:
    def __init__(self, root: Path) -> None:
        db_dir = root / ".booster"
        db_dir.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "stats.db"), check_same_thread=False)
        for stmt in _DDL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
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
        active_days: int = cur.fetchone()[0]

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
            "active_days": active_days,
            "total_reads": total_reads,
            "full_tokens": full_tokens,
            "slice_tokens": slice_tokens,
            "saved_tokens": saved_tokens,
            "savings_pct": savings_pct,
            "top_files": top_files,
        }

    def record_output_session(
        self,
        platform: str,
        verbosity_mode: str,
        output_tokens_actual: int | None,
        output_tokens_estimated: int | None,
    ) -> None:
        is_estimated = 1 if output_tokens_actual is None else 0
        self._conn.execute(
            """INSERT INTO output_sessions
               (ts, platform, verbosity_mode, output_tokens_actual, output_tokens_estimated, is_estimated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now(timezone.utc).date().isoformat(),
                platform,
                verbosity_mode,
                output_tokens_actual,
                output_tokens_estimated,
                is_estimated,
            ),
        )
        self._conn.commit()

    def output_summary(self) -> dict:
        cur = self._conn.cursor()

        cur.execute("SELECT COUNT(*) FROM output_sessions")
        sessions_count: int = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT SUM(output_tokens_actual) FROM output_sessions WHERE is_estimated = 0"
        )
        total_actual: int = cur.fetchone()[0] or 0

        cur.execute(
            "SELECT SUM(output_tokens_estimated) FROM output_sessions WHERE is_estimated = 1"
        )
        total_estimated: int = cur.fetchone()[0] or 0

        cur.execute(
            """SELECT verbosity_mode, COUNT(*), SUM(output_tokens_estimated)
               FROM output_sessions
               GROUP BY verbosity_mode"""
        )
        savings_pct_by_mode: dict[str, float] = {}
        for row in cur.fetchall():
            mode = row[0]
            rate = _VERBOSITY_SAVINGS_RATE.get(mode, 0.0)
            savings_pct_by_mode[mode] = round(rate * 100, 1)

        return {
            "sessions_count": sessions_count,
            "total_actual": total_actual,
            "total_estimated": total_estimated,
            "savings_pct_by_mode": savings_pct_by_mode,
        }
