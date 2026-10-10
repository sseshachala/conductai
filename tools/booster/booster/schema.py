"""SQLite schema for .booster/symbols.db + in-place migrations."""
from __future__ import annotations

import sqlite3

from booster.parsing import split_identifier

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS symbols (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    file      TEXT NOT NULL,
    name      TEXT NOT NULL,
    kind      TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    signature  TEXT NOT NULL DEFAULT '',
    file_hash  TEXT NOT NULL DEFAULT '',
    file_mtime REAL NOT NULL DEFAULT 0.0,
    commit_last_modified TEXT NOT NULL DEFAULT '',
    last_modified_ts INTEGER NOT NULL DEFAULT 0
)
"""

# v0.3.0: call edges between symbols. target_name always set; target_id/target_file
# resolved at query time (cross-file resolution is name-based).
# ponytail: name-based, ~70% accuracy on Python, lower on TS with overloads.
_CREATE_EDGES_TABLE = """
CREATE TABLE IF NOT EXISTS symbol_edges (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   INTEGER NOT NULL,
    target_name TEXT NOT NULL,
    target_file TEXT NOT NULL DEFAULT '',
    target_id   INTEGER NOT NULL DEFAULT 0,
    edge_kind   TEXT NOT NULL DEFAULT 'call',
    file        TEXT NOT NULL,
    line        INTEGER NOT NULL
)
"""

_CREATE_EDGES_INDEX_SOURCE = "CREATE INDEX IF NOT EXISTS idx_edges_source ON symbol_edges(source_id)"
_CREATE_EDGES_INDEX_TARGET = "CREATE INDEX IF NOT EXISTS idx_edges_target_name ON symbol_edges(target_name)"
_CREATE_EDGES_INDEX_FILE = "CREATE INDEX IF NOT EXISTS idx_edges_file ON symbol_edges(file)"

# v0.3.0: test references per symbol. Populated by `booster index --tests`,
# read by test_coverage MCP tool. source='import' for static heuristic,
# 'coverage' for runtime coverage.py data when present.
_CREATE_TESTS_TABLE = """
CREATE TABLE IF NOT EXISTS symbol_tests (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol_id   INTEGER NOT NULL,
    symbol_file TEXT NOT NULL,
    test_file   TEXT NOT NULL,
    test_line   INTEGER NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'import'
)
"""

_CREATE_TESTS_INDEX_SYMBOL = "CREATE INDEX IF NOT EXISTS idx_tests_symbol ON symbol_tests(symbol_id)"
_CREATE_TESTS_INDEX_SYMBOL_FILE = "CREATE INDEX IF NOT EXISTS idx_tests_symbol_file ON symbol_tests(symbol_file)"
_CREATE_TESTS_INDEX_TEST_FILE = "CREATE INDEX IF NOT EXISTS idx_tests_test_file ON symbol_tests(test_file)"

_MIGRATE_ADD_HASH = "ALTER TABLE symbols ADD COLUMN file_hash TEXT NOT NULL DEFAULT ''"
_MIGRATE_ADD_MTIME = "ALTER TABLE symbols ADD COLUMN file_mtime REAL NOT NULL DEFAULT 0.0"
_MIGRATE_ADD_COMMIT = "ALTER TABLE symbols ADD COLUMN commit_last_modified TEXT NOT NULL DEFAULT ''"
_MIGRATE_ADD_TS = "ALTER TABLE symbols ADD COLUMN last_modified_ts INTEGER NOT NULL DEFAULT 0"
_MIGRATE_ADD_DOC = "ALTER TABLE symbols ADD COLUMN doc TEXT NOT NULL DEFAULT ''"

# rowid = symbols.id. `body` = split identifier + signature + doc, so bm25 ranks on
# words rather than raw identifiers. Porter stemming: retry/retries/retrying match.
_CREATE_FTS = (
    "CREATE VIRTUAL TABLE IF NOT EXISTS symbols_fts "
    "USING fts5(name, body, tokenize='porter unicode61')"
)

# v1: doc column + symbols_fts.
_SCHEMA_VERSION = 1


def init_schema(conn: sqlite3.Connection) -> bool:
    """Create/migrate tables. Returns True when FTS5 is available."""
    for ddl in (
        _CREATE_TABLE, _CREATE_EDGES_TABLE, _CREATE_EDGES_INDEX_SOURCE,
        _CREATE_EDGES_INDEX_TARGET, _CREATE_EDGES_INDEX_FILE, _CREATE_TESTS_TABLE,
        _CREATE_TESTS_INDEX_SYMBOL, _CREATE_TESTS_INDEX_SYMBOL_FILE, _CREATE_TESTS_INDEX_TEST_FILE,
    ):
        conn.execute(ddl)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(symbols)").fetchall()}
    for col, ddl in (
        ("file_hash", _MIGRATE_ADD_HASH), ("file_mtime", _MIGRATE_ADD_MTIME),
        ("commit_last_modified", _MIGRATE_ADD_COMMIT), ("last_modified_ts", _MIGRATE_ADD_TS),
        ("doc", _MIGRATE_ADD_DOC),
    ):
        if col not in cols:
            conn.execute(ddl)
    try:
        conn.execute(_CREATE_FTS)
        has_fts = True
    except sqlite3.OperationalError:
        has_fts = False  # sqlite built without FTS5 — search.py falls back to LIKE

    if conn.execute("PRAGMA user_version").fetchone()[0] < _SCHEMA_VERSION:
        if has_fts:
            # Backfill so keyword search works before the next `booster index`.
            conn.execute("DELETE FROM symbols_fts")
            for r in conn.execute("SELECT id, name, signature FROM symbols").fetchall():
                insert_fts(conn, r[0], r[1], r[2], "")
        # Blank hashes so the next index_all re-parses every file and fills `doc`.
        conn.execute("UPDATE symbols SET file_hash = ''")
        conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")
    conn.commit()
    return has_fts


def insert_fts(conn: sqlite3.Connection, sid: int, name: str, signature: str, doc: str) -> None:
    conn.execute(
        "INSERT INTO symbols_fts (rowid, name, body) VALUES (?, ?, ?)",
        (sid, split_identifier(name), f"{split_identifier(signature)} {split_identifier(doc)}"),
    )
