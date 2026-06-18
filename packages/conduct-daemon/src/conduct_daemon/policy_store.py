"""Local SQLite store for policy cache and audit event queue."""
from __future__ import annotations
import json
import sqlite3
import time
from pathlib import Path
from threading import Lock

_DB_PATH = Path.home() / ".conductguard" / "daemon.db"
_lock    = Lock()


def _conn() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS policy_cache (
                workspace_id TEXT NOT NULL,
                persona      TEXT NOT NULL,
                version      TEXT NOT NULL,
                payload      TEXT NOT NULL,
                last_synced  REAL NOT NULL,
                PRIMARY KEY (workspace_id, persona)
            );
            CREATE TABLE IF NOT EXISTS audit_queue (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_id TEXT NOT NULL,
                recorded_at  REAL NOT NULL,
                payload      TEXT NOT NULL
            );
        """)


def get_policy(workspace_id: str, persona: str) -> dict | None:
    with _lock, _conn() as conn:
        row = conn.execute(
            "SELECT payload FROM policy_cache WHERE workspace_id=? AND persona=?",
            (workspace_id, persona),
        ).fetchone()
    return json.loads(row["payload"]) if row else None


def put_policy(payload: dict) -> None:
    workspace_id = payload["workspace_id"]
    persona      = payload.get("persona", "standard")
    version      = payload.get("version", "")
    with _lock, _conn() as conn:
        conn.execute(
            """INSERT INTO policy_cache (workspace_id, persona, version, payload, last_synced)
               VALUES (?,?,?,?,?)
               ON CONFLICT(workspace_id, persona) DO UPDATE SET
                   version=excluded.version,
                   payload=excluded.payload,
                   last_synced=excluded.last_synced""",
            (workspace_id, persona, version, json.dumps(payload), time.time()),
        )


def invalidate(workspace_id: str) -> None:
    with _lock, _conn() as conn:
        conn.execute("DELETE FROM policy_cache WHERE workspace_id=?", (workspace_id,))


def queue_event(workspace_id: str, event: dict) -> None:
    with _lock, _conn() as conn:
        conn.execute(
            "INSERT INTO audit_queue (workspace_id, recorded_at, payload) VALUES (?,?,?)",
            (workspace_id, time.time(), json.dumps(event)),
        )


def drain_events(limit: int = 200) -> list[dict]:
    """Return and delete up to `limit` queued events atomically."""
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT id, payload FROM audit_queue ORDER BY id LIMIT ?", (limit,)
        ).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            conn.execute(f"DELETE FROM audit_queue WHERE id IN ({','.join('?'*len(ids))})", ids)
    return [json.loads(r["payload"]) for r in rows]
