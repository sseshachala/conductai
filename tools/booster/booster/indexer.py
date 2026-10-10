from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path

import numpy as np
from tree_sitter import Parser

from booster.embed import EMBED_MODEL, MODEL_STAMP
from booster.git_util import (  # noqa: F401 — re-exported for existing importers
    _blame_file,
    _changed_lines_since,
    _filter_by_changed_lines,
    _symbol_last_modified,
)
from booster.graph import GraphMixin
from booster.parsing import (  # noqa: F401 — re-exported for existing importers
    PY_LANGUAGE,
    TS_LANGUAGE,
    TSX_LANGUAGE,
    _SKIP_DIRS,
    _TS_EXTENSIONS,
    _attribute_calls,
    _collect_py_calls,
    _collect_py_symbols,
    _collect_ts_calls,
    _collect_ts_symbols,
    _is_test_file,
    _symbol_doc,
    split_identifier,
)
from booster.schema import init_schema, insert_fts
from booster.search import SearchMixin


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def embed_text(name: str, signature: str, doc: str) -> str:
    """What a symbol's vector is built from (passages take no prefix with bge)."""
    return f"{split_identifier(name)} {signature} {doc}".strip()


class SymbolIndexer(SearchMixin, GraphMixin):
    def __init__(self, root: Path) -> None:
        self.root = root
        db_dir = root / ".booster"
        db_dir.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "symbols.db"))
        self._conn.row_factory = sqlite3.Row
        self._has_fts = init_schema(self._conn)
        self._py_parser = Parser(PY_LANGUAGE)
        self._ts_parser = Parser(TS_LANGUAGE)
        self._tsx_parser = Parser(TSX_LANGUAGE)

    def _daemon_embed(self, prefixed_texts: list[str]) -> "np.ndarray | None":
        """Try the running daemon for embeddings; return None if unavailable."""
        from booster.daemon import daemon_embed
        return daemon_embed(prefixed_texts, self.root)

    def _parser_for(self, path: Path) -> Parser:
        if path.suffix == ".tsx" or path.suffix == ".jsx":
            return self._tsx_parser
        if path.suffix in _TS_EXTENSIONS:
            return self._ts_parser
        return self._py_parser

    def _delete_file_rows(self, rel: str) -> None:
        if self._has_fts:
            self._conn.execute(
                "DELETE FROM symbols_fts WHERE rowid IN (SELECT id FROM symbols WHERE file = ?)", (rel,)
            )
        self._conn.execute("DELETE FROM symbol_edges WHERE file = ?", (rel,))
        self._conn.execute("DELETE FROM symbol_tests WHERE symbol_file = ? OR test_file = ?", (rel, rel))
        self._conn.execute("DELETE FROM symbols WHERE file = ?", (rel,))

    def _insert_symbol(self, row: dict) -> int:
        cur = self._conn.execute(
            "INSERT INTO symbols (file, name, kind, start_line, end_line, signature, file_hash, file_mtime,"
            " commit_last_modified, last_modified_ts, doc)"
            " VALUES (:file, :name, :kind, :start_line, :end_line, :signature, :file_hash, :file_mtime,"
            " :commit_last_modified, :last_modified_ts, :doc)",
            {"commit_last_modified": "", "last_modified_ts": 0, "doc": "", **row},
        )
        if self._has_fts:
            insert_fts(self._conn, cur.lastrowid, row["name"], row["signature"], row.get("doc", ""))
        return cur.lastrowid

    def index_file(self, path: Path, fhash: str = "", fmtime: float = 0.0) -> int:
        source = path.read_bytes()
        rel = str(path.relative_to(self.root))
        if not fhash:
            fhash = hashlib.sha256(source).hexdigest()
        if not fmtime:
            fmtime = path.stat().st_mtime
        # Clean up fts/edges/tests tied to old symbols in this file before re-inserting.
        self._delete_file_rows(rel)
        # One git blame per file; empty dict if git unavailable or untracked.
        blame = _blame_file(path, self.root)
        lines = source.decode("utf-8", errors="replace").splitlines()

        is_ts = path.suffix in _TS_EXTENSIONS
        tree = self._parser_for(path).parse(source)
        collect = _collect_ts_symbols if is_ts else _collect_py_symbols
        inserted = 0
        for name, kind, start_line, end_line, sig in collect(tree.root_node, source):
            sha, ts = _symbol_last_modified(blame, start_line, end_line)
            self._insert_symbol({
                "file": rel, "name": name, "kind": kind, "start_line": start_line,
                "end_line": end_line, "signature": sig, "file_hash": fhash, "file_mtime": fmtime,
                "commit_last_modified": sha, "last_modified_ts": ts,
                "doc": _symbol_doc(lines, start_line, end_line),
            })
            inserted += 1

        # Call-edge extraction (v0.3.0). Same-file resolution only at index time;
        # cross-file name resolution happens at expand_calls query time.
        calls = _collect_ts_calls(tree.root_node, source) if is_ts else _collect_py_calls(tree.root_node, source)
        if calls:
            sym_rows = self._conn.execute(
                "SELECT id, start_line, end_line, name FROM symbols WHERE file = ?", (rel,)
            ).fetchall()
            sym_intervals = [(r["id"], r["start_line"], r["end_line"]) for r in sym_rows]
            name_to_id = {r["name"]: r["id"] for r in sym_rows}
            for source_id, callee, line in _attribute_calls(calls, sym_intervals):
                target_id = name_to_id.get(callee, 0)
                target_file = rel if target_id else ""
                self._conn.execute(
                    "INSERT INTO symbol_edges (source_id, target_name, target_file, target_id, file, line)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (source_id, callee, target_file, target_id, rel, line),
                )

        self._conn.commit()
        return inserted

    def _is_unchanged(self, rel: str, fhash: str, fmtime: float) -> bool:
        row = self._conn.execute(
            "SELECT file_hash, file_mtime FROM symbols WHERE file = ? LIMIT 1", (rel,)
        ).fetchone()
        return row is not None and row["file_hash"] == fhash and abs(row["file_mtime"] - fmtime) < 0.001

    def index_all(self, embed: bool = False, force: bool = False) -> tuple[int, int]:
        """Index all source files. Skips unchanged files unless force=True."""
        if force:
            if self._has_fts:
                self._conn.execute("DELETE FROM symbols_fts")
            self._conn.execute("DELETE FROM symbol_edges")
            self._conn.execute("DELETE FROM symbol_tests")
            self._conn.execute("DELETE FROM symbols")
            self._conn.commit()

        files = 0
        skipped = 0
        symbols = 0
        patterns = ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx"]
        for pattern in patterns:
            for path in self.root.rglob(pattern):
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                try:
                    rel = str(path.relative_to(self.root))
                    fmtime = path.stat().st_mtime
                    fhash = _file_hash(path)
                    if not force and self._is_unchanged(rel, fhash, fmtime):
                        skipped += 1
                        continue
                    symbols += self.index_file(path, fhash=fhash, fmtime=fmtime)
                    files += 1
                except Exception:
                    pass
        if embed:
            self.build_embeddings()
        return files, symbols

    def build_embeddings(self) -> int:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: F401
        except ImportError:
            raise SystemExit("Semantic search requires: pip install agent-booster[embed]")
        from booster.embed import encode

        rows = self._conn.execute("SELECT id, name, signature, doc FROM symbols ORDER BY id").fetchall()
        if not rows:
            return 0

        ids = np.array([r["id"] for r in rows], dtype=np.int64)
        texts = [embed_text(r["name"], r["signature"], r["doc"]) for r in rows]
        vecs = self._daemon_embed(texts)
        vecs = encode(texts) if vecs is None else vecs

        db_dir = self.root / ".booster"
        np.save(str(db_dir / "vectors.npy"), vecs)
        np.save(str(db_dir / "vector_ids.npy"), ids)
        (db_dir / MODEL_STAMP).write_text(EMBED_MODEL)
        return len(rows)

    def get_symbols(self, file: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE file = ? ORDER BY start_line", (file,)
        ).fetchall()
        return [dict(r) for r in rows]

    def export_symbols(self) -> list[dict]:
        """Export all symbols as plain dicts (for shared index push)."""
        rows = self._conn.execute(
            "SELECT file, name, kind, start_line, end_line, signature, file_hash, file_mtime FROM symbols ORDER BY file, start_line"
        ).fetchall()
        return [dict(r) for r in rows]

    def import_symbols(self, symbols: list[dict]) -> int:
        """Merge incoming symbols from team index. Skips files already indexed locally with same hash."""
        imported = 0
        for s in symbols:
            existing = self._conn.execute(
                "SELECT file_hash FROM symbols WHERE file = ? LIMIT 1", (s["file"],)
            ).fetchone()
            if existing and existing["file_hash"] == s.get("file_hash"):
                continue
            self._insert_symbol(s)
            imported += 1
        self._conn.commit()
        return imported

    @staticmethod
    def repo_key(root: Path) -> str:
        """Stable key for this repo — git remote origin URL or root path hash."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=root, capture_output=True, text=True, timeout=3
            )
            if result.returncode == 0 and result.stdout.strip():
                return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:16]
        except Exception:
            pass
        return hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
