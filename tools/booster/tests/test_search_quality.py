"""bm25 keyword search, doc snippets, schema migration, model-stamped vectors."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from booster.indexer import SymbolIndexer
from booster.parsing import _symbol_doc, split_identifier


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _names(results: list[dict]) -> list[str]:
    return [r["name"] for r in results]


def test_split_identifier():
    assert split_identifier("_sendWithBackoff") == "send with backoff"
    assert split_identifier("send_with_backoff") == "send with backoff"
    assert split_identifier("HTTPServerError") == "http server error"


def test_symbol_doc_takes_leading_comment_and_body():
    lines = ["// Retries on 429.", "function go() {", "  return 1;", "}"]
    assert _symbol_doc(lines, 2, 4) == "// Retries on 429. return 1; }"


def test_search_matches_docstring_words(tmp_path):
    _write(tmp_path, "net.py", (
        "def _send_with_backoff(req):\n"
        '    """Retry the request when the provider rate limits us (429)."""\n'
        "    return req\n\n"
        "def parse_config(path):\n"
        "    return path\n"
    ))
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    # No query word appears in the name; the docstring carries it. "retries" stems to "retri".
    assert _names(ix.search("where do we handle retries on rate limits"))[0] == "_send_with_backoff"


def test_search_any_term_and_camel_case(tmp_path):
    _write(tmp_path, "api.ts", "export function sendWithBackoff(r: Req) { return r }\n")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    # Old LIKE search required every term to match; "nonexistentword" would drop it.
    assert _names(ix.search("send backoff nonexistentword")) == ["sendWithBackoff"]


def test_search_scoped_to_file(tmp_path):
    _write(tmp_path, "a.py", "def load_user(): pass\n")
    _write(tmp_path, "b.py", "def load_user(): pass\n")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    assert [r["file"] for r in ix.search("load user", file="b.py")] == ["b.py"]


def test_reindex_drops_stale_fts_rows(tmp_path):
    p = _write(tmp_path, "m.py", "def old_name(): pass\n")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    p.write_text("def new_name(): pass\n")
    ix.index_file(p)
    assert ix.search("old") == []
    assert _names(ix.search("new")) == ["new_name"]


def test_migrates_pre_fts_database(tmp_path):
    db_dir = tmp_path / ".booster"
    db_dir.mkdir()
    conn = sqlite3.connect(str(db_dir / "symbols.db"))
    conn.execute(
        "CREATE TABLE symbols (id INTEGER PRIMARY KEY AUTOINCREMENT, file TEXT NOT NULL,"
        " name TEXT NOT NULL, kind TEXT NOT NULL, start_line INTEGER NOT NULL,"
        " end_line INTEGER NOT NULL, signature TEXT NOT NULL DEFAULT '',"
        " file_hash TEXT NOT NULL DEFAULT '', file_mtime REAL NOT NULL DEFAULT 0.0)"
    )
    conn.execute(
        "INSERT INTO symbols (file, name, kind, start_line, end_line, signature, file_hash)"
        " VALUES ('x.py', 'charge_card', 'function', 1, 2, 'def charge_card(amount):', 'abc')"
    )
    conn.commit()
    conn.close()

    ix = SymbolIndexer(tmp_path)
    assert _names(ix.search("charge card")) == ["charge_card"]  # backfilled
    row = ix._conn.execute("SELECT file_hash, doc FROM symbols").fetchone()
    assert row["file_hash"] == ""  # forces re-parse so doc gets filled
    assert ix._conn.execute("PRAGMA user_version").fetchone()[0] >= 1


def test_vectors_from_other_model_are_ignored(tmp_path):
    _write(tmp_path, "m.py", "def compute_tax(x): pass\n")
    ix = SymbolIndexer(tmp_path)
    ix.index_all()
    sid = ix._conn.execute("SELECT id FROM symbols").fetchone()[0]
    db = tmp_path / ".booster"
    np.save(str(db / "vectors.npy"), np.ones((1, 384), dtype=np.float32))
    np.save(str(db / "vector_ids.npy"), np.array([sid]))
    (db / "vectors_model.txt").write_text("all-MiniLM-L6-v2")
    # Stale stamp → keyword fallback, never touches the embedding model.
    assert _names(ix.vector_search("compute tax")) == ["compute_tax"]
