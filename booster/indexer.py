from __future__ import annotations

import hashlib
import sqlite3
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _ST

_embed_model: "_ST | None" = None

# Asymmetric embedding prefixes: separate instruction for indexing vs querying.
# "passage:" prefix tells the model this is a document to store.
# "query:" prefix tells the model this is a question/task to match against documents.
_EMBED_INDEX_PREFIX = "passage: "
_EMBED_QUERY_PREFIX = "query: "


def _get_embed_model() -> "_ST":
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer("all-MiniLM-L6-v2")
    return _embed_model


def _embed_for_index(texts: list[str]) -> "np.ndarray":
    model = _get_embed_model()
    prefixed = [f"{_EMBED_INDEX_PREFIX}{t}" for t in texts]
    return model.encode(prefixed, show_progress_bar=False, convert_to_numpy=True)


def _embed_for_query(query: str) -> "np.ndarray":
    model = _get_embed_model()
    return model.encode([f"{_EMBED_QUERY_PREFIX}{query}"], show_progress_bar=False, convert_to_numpy=True)[0]


def _normalize(vecs: "np.ndarray") -> "np.ndarray":
    norms = np.linalg.norm(vecs, axis=0 if vecs.ndim == 1 else 1, keepdims=vecs.ndim > 1)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


PY_LANGUAGE = Language(tspython.language())
TS_LANGUAGE = Language(tsts.language_typescript())
TSX_LANGUAGE = Language(tsts.language_tsx())

_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", ".booster", "worktrees", ".next", "dist", "build"}

_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}

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

_PY_KIND_MAP = {
    "function_definition": "function",
    "class_definition": "class",
}

_TS_KIND_MAP = {
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
}


def _extract_name(node: Node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""


def _extract_ts_name(node: Node, source: bytes) -> str:
    if node.type == "method_definition":
        for child in node.children:
            if child.type == "property_identifier":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    else:
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""


def _keyword_match(symbols: list[dict], query: str, limit: int) -> list[dict]:
    keywords = [w.lower() for w in query.split() if len(w) > 2]
    if not keywords:
        return symbols[:limit]
    matched = [
        s for s in symbols
        if any(kw in s["name"].lower() or kw in s["signature"].lower() for kw in keywords)
    ]
    return matched[:limit]


def _extract_signature(node: Node, source: bytes) -> str:
    first_line_end = source.find(b"\n", node.start_byte)
    if first_line_end == -1:
        first_line_end = node.end_byte
    return source[node.start_byte:first_line_end].decode("utf-8", errors="replace").strip()[:300]


def _collect_ts_symbols(root_node: Node, source: bytes) -> list[tuple[str, str, int, int, str]]:
    """Walk TS/TSX AST, returning (name, kind, start_line, end_line, signature) tuples."""
    results: list[tuple[str, str, int, int, str]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type in _TS_KIND_MAP:
            name = _extract_ts_name(node, source)
            if name:
                sig = _extract_signature(node, source)
                results.append((name, _TS_KIND_MAP[node.type], node.start_point[0] + 1, node.end_point[0] + 1, sig))
        elif node.type == "lexical_declaration":
            # const foo = (...) => { ... }  — extract named arrow functions
            for declarator in node.children:
                if declarator.type != "variable_declarator":
                    continue
                has_arrow = any(c.type == "arrow_function" for c in declarator.children)
                if not has_arrow:
                    continue
                name = ""
                arrow_node: Node | None = None
                for child in declarator.children:
                    if child.type == "identifier" and not name:
                        name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    if child.type == "arrow_function":
                        arrow_node = child
                if name and arrow_node:
                    sig = _extract_signature(declarator, source)
                    results.append((name, "function", arrow_node.start_point[0] + 1, arrow_node.end_point[0] + 1, sig))
                    continue  # don't recurse into arrow body for nested arrows
        stack.extend(node.children)
    return results


def _collect_py_calls(root_node: Node, source: bytes) -> list[tuple[str, int]]:
    """Walk Python AST for call sites, return (callee_name, line) tuples.

    ponytail: name-based; obj.foo() → 'foo', mod.cls.foo() → 'foo'.
    Cross-file resolution and method dispatch are resolved at query time.
    """
    calls: list[tuple[str, int]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "call" and node.children:
            fn = node.children[0]
            name = ""
            if fn.type == "identifier":
                name = source[fn.start_byte:fn.end_byte].decode("utf-8", errors="replace")
            elif fn.type == "attribute":
                for c in reversed(fn.children):
                    if c.type == "identifier":
                        name = source[c.start_byte:c.end_byte].decode("utf-8", errors="replace")
                        break
            if name:
                calls.append((name, node.start_point[0] + 1))
        stack.extend(node.children)
    return calls


def _collect_ts_calls(root_node: Node, source: bytes) -> list[tuple[str, int]]:
    """Walk TS/TSX AST for call sites, return (callee_name, line) tuples."""
    calls: list[tuple[str, int]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "call_expression" and node.children:
            fn = node.children[0]
            name = ""
            if fn.type == "identifier":
                name = source[fn.start_byte:fn.end_byte].decode("utf-8", errors="replace")
            elif fn.type == "member_expression":
                for c in reversed(fn.children):
                    if c.type == "property_identifier":
                        name = source[c.start_byte:c.end_byte].decode("utf-8", errors="replace")
                        break
            if name:
                calls.append((name, node.start_point[0] + 1))
        stack.extend(node.children)
    return calls


def _attribute_calls(
    calls: list[tuple[str, int]],
    symbols: list[tuple[int, int, int]],
) -> list[tuple[int, str, int]]:
    """Map each call to its enclosing symbol via line containment.

    symbols: list of (symbol_id, start_line, end_line).
    Returns: list of (source_symbol_id, callee_name, call_line).
    Skips calls not contained in any indexed symbol (module-level code).
    """
    # Sort symbols by range size ascending so the innermost match wins.
    ranked = sorted(symbols, key=lambda s: s[2] - s[1])
    out: list[tuple[int, str, int]] = []
    for callee, line in calls:
        for sid, s, e in ranked:
            if s <= line <= e:
                out.append((sid, callee, line))
                break
    return out


_TEST_FILE_PATTERNS = [
    "test_*.py", "*_test.py", "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx",
    "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx",
]


def _is_test_file(rel: str) -> bool:
    """Check whether a relative path looks like a test file."""
    name = Path(rel).name
    parts = Path(rel).parts
    if any(part in ("tests", "__tests__", "test") for part in parts):
        return True
    # quick pattern match against final filename
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        if name.endswith(f".test{ext}") or name.endswith(f".spec{ext}"):
            return True
    return False


def _changed_lines_since(root: Path, since: str) -> dict[str, set[int]]:
    """Return {file_rel: {changed_line_numbers}} for files modified since git ref.

    Empty dict if git is unavailable, ref is invalid, or any error occurs.
    Uses git diff --unified=0 against the current working tree (includes uncommitted).
    """
    try:
        r = subprocess.run(
            ["git", "diff", "--unified=0", since, "--"],
            cwd=str(root), capture_output=True, text=True, timeout=30,
        )
        if r.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}

    out: dict[str, set[int]] = {}
    cur_file = ""
    for line in r.stdout.splitlines():
        if line.startswith("+++ b/"):
            cur_file = line[6:]
            out.setdefault(cur_file, set())
        elif line.startswith("+++ /dev/null"):
            cur_file = ""  # file deletion; skip
        elif line.startswith("@@ ") and cur_file:
            # @@ -X,Y +A,B @@  → we want lines A through A+B-1 on the new side
            try:
                plus = line.split("+", 1)[1].split(" ", 1)[0]
                if "," in plus:
                    start_s, count_s = plus.split(",")
                    start, count = int(start_s), int(count_s)
                else:
                    start, count = int(plus), 1
                if count > 0:
                    out[cur_file].update(range(start, start + count))
            except (IndexError, ValueError):
                continue
    return out


def _filter_by_changed_lines(
    symbols: list[dict], changed: dict[str, set[int]]
) -> list[dict]:
    """Keep symbols whose [start_line, end_line] overlaps the changed line set for their file."""
    out: list[dict] = []
    for s in symbols:
        file_changes = changed.get(s["file"])
        if not file_changes:
            continue
        for ln in range(s["start_line"], s["end_line"] + 1):
            if ln in file_changes:
                out.append(s)
                break
    return out


def _blame_file(path: Path, root: Path) -> dict[int, tuple[str, int]]:
    """Return {line_number: (commit_sha, author_unix_ts)} for every line in path.

    One `git blame --line-porcelain` subprocess per file. Returns empty dict if
    git is absent, file is untracked, or any error occurs (callers should treat
    missing entries as "unknown last_modified" and leave the symbol fields at default).
    """
    try:
        rel = str(path.relative_to(root))
        r = subprocess.run(
            ["git", "blame", "--line-porcelain", "--", rel],
            cwd=str(root), capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return {}
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        return {}

    out: dict[int, tuple[str, int]] = {}
    cur_sha = ""
    cur_ts = 0
    for raw in r.stdout.splitlines():
        if not raw:
            continue
        if raw.startswith("\t"):
            # content line — nothing to do, just consumes the chunk
            continue
        parts = raw.split(" ", 3)
        first = parts[0]
        # header line: <sha> <orig_line> <final_line> [<count>]
        # 40-char hex sha, followed by digits in parts[1..]
        if len(first) == 40 and all(c in "0123456789abcdef" for c in first):
            cur_sha = first
            try:
                final_line = int(parts[2])
                out[final_line] = (cur_sha, cur_ts)
            except (IndexError, ValueError):
                pass
        elif first == "author-time" and len(parts) >= 2:
            try:
                cur_ts = int(parts[1])
                # backfill the most-recent header (header came before metadata)
                if out:
                    last_line = next(reversed(out))
                    sha_at_last = out[last_line][0]
                    if sha_at_last == cur_sha:
                        out[last_line] = (sha_at_last, cur_ts)
            except (IndexError, ValueError):
                pass
    return out


def _symbol_last_modified(blame: dict[int, tuple[str, int]], start: int, end: int) -> tuple[str, int]:
    """Pick the most recent (sha, ts) across the symbol's line range."""
    best_ts = 0
    best_sha = ""
    for ln in range(start, end + 1):
        entry = blame.get(ln)
        if entry and entry[1] > best_ts:
            best_sha, best_ts = entry
    return best_sha, best_ts


class SymbolIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root
        db_dir = root / ".booster"
        db_dir.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "symbols.db"))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.execute(_CREATE_EDGES_TABLE)
        self._conn.execute(_CREATE_EDGES_INDEX_SOURCE)
        self._conn.execute(_CREATE_EDGES_INDEX_TARGET)
        self._conn.execute(_CREATE_EDGES_INDEX_FILE)
        self._conn.execute(_CREATE_TESTS_TABLE)
        self._conn.execute(_CREATE_TESTS_INDEX_SYMBOL)
        self._conn.execute(_CREATE_TESTS_INDEX_SYMBOL_FILE)
        self._conn.execute(_CREATE_TESTS_INDEX_TEST_FILE)
        self._conn.commit()
        self._migrate()
        self._py_parser = Parser(PY_LANGUAGE)
        self._ts_parser = Parser(TS_LANGUAGE)
        self._tsx_parser = Parser(TSX_LANGUAGE)

    def _daemon_embed(self, prefixed_texts: list[str]) -> "np.ndarray | None":
        """Try the running daemon for embeddings; return None if unavailable."""
        from booster.daemon import daemon_embed
        return daemon_embed(prefixed_texts, self.root)

    def _migrate(self) -> None:
        cols = {row[1] for row in self._conn.execute("PRAGMA table_info(symbols)").fetchall()}
        if "file_hash" not in cols:
            self._conn.execute(_MIGRATE_ADD_HASH)
        if "file_mtime" not in cols:
            self._conn.execute(_MIGRATE_ADD_MTIME)
        if "commit_last_modified" not in cols:
            self._conn.execute(_MIGRATE_ADD_COMMIT)
        if "last_modified_ts" not in cols:
            self._conn.execute(_MIGRATE_ADD_TS)
        self._conn.commit()

    def _parser_for(self, path: Path) -> Parser:
        if path.suffix == ".tsx" or path.suffix == ".jsx":
            return self._tsx_parser
        if path.suffix in _TS_EXTENSIONS:
            return self._ts_parser
        return self._py_parser

    def index_file(self, path: Path, fhash: str = "", fmtime: float = 0.0) -> int:
        source = path.read_bytes()
        rel = str(path.relative_to(self.root))
        if not fhash:
            fhash = hashlib.sha256(source).hexdigest()
        if not fmtime:
            fmtime = path.stat().st_mtime
        # Clean up edges/tests tied to old symbols in this file before re-inserting.
        self._conn.execute("DELETE FROM symbol_edges WHERE file = ?", (rel,))
        self._conn.execute("DELETE FROM symbol_tests WHERE symbol_file = ? OR test_file = ?", (rel, rel))
        self._conn.execute("DELETE FROM symbols WHERE file = ?", (rel,))
        inserted = 0
        # One git blame per file; empty dict if git unavailable or untracked.
        blame = _blame_file(path, self.root)

        if path.suffix in _TS_EXTENSIONS:
            parser = self._parser_for(path)
            tree = parser.parse(source)
            for name, kind, start_line, end_line, sig in _collect_ts_symbols(tree.root_node, source):
                sha, ts = _symbol_last_modified(blame, start_line, end_line)
                self._conn.execute(
                    "INSERT INTO symbols (file, name, kind, start_line, end_line, signature, file_hash, file_mtime, commit_last_modified, last_modified_ts)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (rel, name, kind, start_line, end_line, sig, fhash, fmtime, sha, ts),
                )
                inserted += 1
        else:
            tree = self._py_parser.parse(source)
            cursor = [tree.root_node]
            while cursor:
                node = cursor.pop()
                if node.type in _PY_KIND_MAP:
                    name = _extract_name(node, source)
                    if name:
                        sig = _extract_signature(node, source)
                        s_line = node.start_point[0] + 1
                        e_line = node.end_point[0] + 1
                        sha, ts = _symbol_last_modified(blame, s_line, e_line)
                        self._conn.execute(
                            "INSERT INTO symbols (file, name, kind, start_line, end_line, signature, file_hash, file_mtime, commit_last_modified, last_modified_ts)"
                            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (rel, name, _PY_KIND_MAP[node.type], s_line, e_line, sig, fhash, fmtime, sha, ts),
                        )
                        inserted += 1
                cursor.extend(node.children)

        # Call-edge extraction (v0.3.0). Same-file resolution only at index time;
        # cross-file name resolution happens at expand_calls query time.
        if path.suffix in _TS_EXTENSIONS:
            calls = _collect_ts_calls(tree.root_node, source)
        else:
            calls = _collect_py_calls(tree.root_node, source)
        if calls:
            sym_rows = self._conn.execute(
                "SELECT id, start_line, end_line, name FROM symbols WHERE file = ?", (rel,)
            ).fetchall()
            sym_intervals = [(r["id"], r["start_line"], r["end_line"]) for r in sym_rows]
            name_to_id = {r["name"]: r["id"] for r in sym_rows}
            attributed = _attribute_calls(calls, sym_intervals)
            for source_id, callee, line in attributed:
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

        rows = self._conn.execute("SELECT id, name, signature FROM symbols ORDER BY id").fetchall()
        if not rows:
            return 0

        ids = np.array([r["id"] for r in rows], dtype=np.int64)
        raw_texts = [f"{r['name']} {r['signature']}" for r in rows]
        prefixed = [f"{_EMBED_INDEX_PREFIX}{t}" for t in raw_texts]
        vecs = self._daemon_embed(prefixed)
        if vecs is None:
            vecs = _embed_for_index(raw_texts)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        vecs = vecs / norms

        db_dir = self.root / ".booster"
        np.save(str(db_dir / "vectors.npy"), vecs)
        np.save(str(db_dir / "vector_ids.npy"), ids)
        return len(rows)

    def vector_search(self, query: str, limit: int = 10) -> list[dict]:
        db_dir = self.root / ".booster"
        vec_path = db_dir / "vectors.npy"
        ids_path = db_dir / "vector_ids.npy"

        if not vec_path.exists() or not ids_path.exists():
            return self.search(query, limit)

        try:
            _get_embed_model()
        except (ImportError, Exception):
            return self.search(query, limit)

        vecs = np.load(str(vec_path))
        ids = np.load(str(ids_path))

        prefixed_q = f"{_EMBED_QUERY_PREFIX}{query}"
        daemon_result = self._daemon_embed([prefixed_q])
        if daemon_result is not None:
            q = _normalize(daemon_result[0])
        else:
            q = _normalize(_embed_for_query(query))

        scores = vecs @ q
        top_k = min(limit, len(scores))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        symbol_ids = [int(ids[i]) for i in top_indices]
        placeholders = ",".join("?" * len(symbol_ids))
        rows = self._conn.execute(
            f"SELECT * FROM symbols WHERE id IN ({placeholders})", symbol_ids
        ).fetchall()

        id_to_row = {r["id"]: dict(r) for r in rows}
        return [id_to_row[sid] for sid in symbol_ids if sid in id_to_row]

    def vector_search_file(self, file: str, query: str, limit: int = 5) -> list[dict]:
        """Vector search restricted to symbols in a single file."""
        file_symbols = self.get_symbols(file)
        if not file_symbols:
            return []

        db_dir = self.root / ".booster"
        vec_path = db_dir / "vectors.npy"
        ids_path = db_dir / "vector_ids.npy"

        if not vec_path.exists() or not ids_path.exists():
            return _keyword_match(file_symbols, query, limit)

        try:
            _get_embed_model()
        except (ImportError, Exception):
            return _keyword_match(file_symbols, query, limit)

        file_id_set = {s["id"] for s in file_symbols}
        all_ids = np.load(str(ids_path))
        mask = np.array([int(i) in file_id_set for i in all_ids])
        if not mask.any():
            return _keyword_match(file_symbols, query, limit)

        all_vecs = np.load(str(vec_path))
        file_vecs = all_vecs[mask]
        file_ids_ordered = [int(all_ids[i]) for i in range(len(all_ids)) if mask[i]]

        prefixed_q = f"{_EMBED_QUERY_PREFIX}{query}"
        daemon_result = self._daemon_embed([prefixed_q])
        if daemon_result is not None:
            q = _normalize(daemon_result[0])
        else:
            q = _normalize(_embed_for_query(query))

        scores = file_vecs @ q
        top_k = min(limit, len(scores))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        id_to_sym = {s["id"]: s for s in file_symbols}
        return [id_to_sym[file_ids_ordered[i]] for i in top_indices if file_ids_ordered[i] in id_to_sym]

    def rrf_search(self, query: str, limit: int = 10, k: int = 60) -> list[dict]:
        """Reciprocal Rank Fusion of vector + keyword results.

        Merges two ranked lists using RRF score = sum(1 / (k + rank_i)).
        Falls back to keyword-only when embeddings are unavailable.
        """
        kw_results = self.search(query, limit=limit * 2)
        vec_results = self.vector_search(query, limit=limit * 2)

        kw_ids = [r["id"] for r in kw_results]
        vec_ids = [r["id"] for r in vec_results]
        if kw_ids == vec_ids:
            return kw_results[:limit]

        kw_rank = {r["id"]: i for i, r in enumerate(kw_results)}
        vec_rank = {r["id"]: i for i, r in enumerate(vec_results)}
        all_ids = list(dict.fromkeys(kw_ids + vec_ids))

        def _score(sid: int) -> float:
            s = 0.0
            if sid in kw_rank:
                s += 1.0 / (k + kw_rank[sid])
            if sid in vec_rank:
                s += 1.0 / (k + vec_rank[sid])
            return s

        ranked_ids = sorted(all_ids, key=_score, reverse=True)[:limit]
        id_to_sym = {r["id"]: r for r in kw_results + vec_results}
        return [id_to_sym[sid] for sid in ranked_ids if sid in id_to_sym]

    def rrf_search_file(self, file: str, query: str, limit: int = 5, k: int = 60) -> list[dict]:
        """RRF search restricted to symbols in a single file."""
        file_symbols = self.get_symbols(file)
        if not file_symbols:
            return []

        kw_results = _keyword_match(file_symbols, query, limit=limit * 2)
        vec_results = self.vector_search_file(file, query, limit=limit * 2)

        if [r["id"] for r in kw_results] == [r["id"] for r in vec_results]:
            return kw_results[:limit]

        kw_rank = {r["id"]: i for i, r in enumerate(kw_results)}
        vec_rank = {r["id"]: i for i, r in enumerate(vec_results)}
        all_ids = list(dict.fromkeys([r["id"] for r in kw_results] + [r["id"] for r in vec_results]))

        def _score(sid: int) -> float:
            s = 0.0
            if sid in kw_rank:
                s += 1.0 / (k + kw_rank[sid])
            if sid in vec_rank:
                s += 1.0 / (k + vec_rank[sid])
            return s

        ranked_ids = sorted(all_ids, key=_score, reverse=True)[:limit]
        id_to_sym = {s["id"]: s for s in file_symbols}
        return [id_to_sym[sid] for sid in ranked_ids if sid in id_to_sym]

    def index_tests(self) -> tuple[int, int]:
        """Populate symbol_tests by scanning test files for symbol-name references.

        Returns (test_files_scanned, references_recorded).
        ponytail: coarse substring match. False positives possible when a symbol
        name appears in test text without being the real target. Upgrade path:
        parse imports via tree-sitter, or read coverage.py runtime data.
        """
        # Wipe and rebuild — cheap given the table is small relative to symbols.
        self._conn.execute("DELETE FROM symbol_tests")

        # Build symbol name -> [(symbol_id, symbol_file)] index.
        sym_index: dict[str, list[tuple[int, str]]] = {}
        for r in self._conn.execute(
            "SELECT id, file, name FROM symbols WHERE name NOT LIKE '\\_%' ESCAPE '\\'"
        ).fetchall():
            sym_index.setdefault(r["name"], []).append((r["id"], r["file"]))

        test_files = 0
        refs = 0
        patterns = ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx"]
        seen: set[tuple[int, str]] = set()
        for pattern in patterns:
            for path in self.root.rglob(pattern):
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                try:
                    rel = str(path.relative_to(self.root))
                except ValueError:
                    continue
                if not _is_test_file(rel):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                test_files += 1
                # Cheap word-boundary substring check; iterate names that are
                # >=3 chars to avoid noisy hits on common short tokens.
                for sym_name, locations in sym_index.items():
                    if len(sym_name) < 3:
                        continue
                    if sym_name not in text:
                        continue
                    for sid, sfile in locations:
                        if sfile == rel:
                            continue  # don't record a test file's own symbols against itself
                        key = (sid, rel)
                        if key in seen:
                            continue
                        seen.add(key)
                        self._conn.execute(
                            "INSERT INTO symbol_tests (symbol_id, symbol_file, test_file, test_line, source)"
                            " VALUES (?, ?, ?, ?, ?)",
                            (sid, sfile, rel, 0, "import"),
                        )
                        refs += 1
        self._conn.commit()
        return test_files, refs

    def test_coverage(self, symbol: str, file: str | None = None) -> list[dict]:
        """Return test references for symbol(s) matching name (+ optional file filter)."""
        if file:
            rows = self._conn.execute(
                """SELECT t.test_file, t.test_line, t.source, s.file AS symbol_file, s.name
                     FROM symbol_tests t
                     JOIN symbols s ON s.id = t.symbol_id
                    WHERE s.name = ? AND s.file = ?
                    ORDER BY t.test_file""",
                (symbol, file),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT t.test_file, t.test_line, t.source, s.file AS symbol_file, s.name
                     FROM symbol_tests t
                     JOIN symbols s ON s.id = t.symbol_id
                    WHERE s.name = ?
                    ORDER BY t.test_file""",
                (symbol,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_symbols(self, file: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE file = ? ORDER BY start_line", (file,)
        ).fetchall()
        return [dict(r) for r in rows]

    def expand_calls(
        self,
        symbol_name: str,
        direction: str = "callers",
        depth: int = 1,
        file: str | None = None,
    ) -> list[dict]:
        """Return immediate callers or callees of a symbol.

        direction: 'callers' (who calls symbol_name) | 'callees' (what symbol_name calls) | 'both'.
        depth: 1 by default, max 3. Each level expands the frontier; cycle-safe.
        file: optional file filter to disambiguate when symbol_name appears in multiple files.

        Cross-file resolution is name-based at query time: if target_id is 0,
        match by target_name against indexed symbols. Documented limit: false
        positives possible when the same name exists in multiple unrelated files.
        """
        depth = max(1, min(depth, 3))
        directions = {"callers", "callees"} if direction == "both" else {direction}

        # Resolve seed symbol ids
        if file:
            seed_rows = self._conn.execute(
                "SELECT id, file, name FROM symbols WHERE name = ? AND file = ?",
                (symbol_name, file),
            ).fetchall()
        else:
            seed_rows = self._conn.execute(
                "SELECT id, file, name FROM symbols WHERE name = ?", (symbol_name,)
            ).fetchall()
        if not seed_rows:
            return []

        results: list[dict] = []
        seen: set[tuple[str, int, str]] = set()  # (edge_kind_dir, edge_id, target)
        frontier_ids = {r["id"] for r in seed_rows}
        frontier_names = {r["name"] for r in seed_rows}

        for level in range(depth):
            next_ids: set[int] = set()
            next_names: set[str] = set()

            if "callees" in directions and frontier_ids:
                placeholders = ",".join("?" * len(frontier_ids))
                rows = self._conn.execute(
                    f"""SELECT e.id AS edge_id, e.source_id, e.target_name, e.target_file,
                               e.target_id, e.line, s.file AS src_file, s.name AS src_name
                          FROM symbol_edges e
                          JOIN symbols s ON s.id = e.source_id
                         WHERE e.source_id IN ({placeholders})""",
                    list(frontier_ids),
                ).fetchall()
                for r in rows:
                    key = ("out", r["edge_id"], r["target_name"])
                    if key in seen:
                        continue
                    seen.add(key)
                    # Resolve target if unresolved at index time
                    tid, tfile = r["target_id"], r["target_file"]
                    if not tid:
                        match = self._conn.execute(
                            "SELECT id, file FROM symbols WHERE name = ? LIMIT 2",
                            (r["target_name"],),
                        ).fetchall()
                        if len(match) == 1:
                            tid, tfile = match[0]["id"], match[0]["file"]
                    results.append({
                        "direction": "callee",
                        "depth": level + 1,
                        "from_file": r["src_file"],
                        "from_name": r["src_name"],
                        "to_file": tfile,
                        "to_name": r["target_name"],
                        "to_id": tid,
                        "call_line": r["line"],
                    })
                    if tid:
                        next_ids.add(tid)
                    next_names.add(r["target_name"])

            if "callers" in directions and frontier_names:
                placeholders = ",".join("?" * len(frontier_names))
                rows = self._conn.execute(
                    f"""SELECT e.id AS edge_id, e.source_id, e.target_name, e.line,
                               s.file AS src_file, s.name AS src_name, s.id AS src_id
                          FROM symbol_edges e
                          JOIN symbols s ON s.id = e.source_id
                         WHERE e.target_name IN ({placeholders})""",
                    list(frontier_names),
                ).fetchall()
                for r in rows:
                    key = ("in", r["edge_id"], r["target_name"])
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append({
                        "direction": "caller",
                        "depth": level + 1,
                        "from_file": r["src_file"],
                        "from_name": r["src_name"],
                        "from_id": r["src_id"],
                        "to_name": r["target_name"],
                        "call_line": r["line"],
                    })
                    next_ids.add(r["src_id"])
                    next_names.add(r["src_name"])

            frontier_ids = next_ids
            frontier_names = next_names

        return results

    def search(self, query: str, limit: int = 10) -> list[dict]:
        terms = query.lower().split()
        if not terms:
            return []
        conditions = " AND ".join(
            "(LOWER(name) LIKE ? OR LOWER(signature) LIKE ?)" for _ in terms
        )
        params: list[str] = []
        for t in terms:
            params.extend([f"%{t}%", f"%{t}%"])
        params.append(str(limit))
        rows = self._conn.execute(
            f"SELECT * FROM symbols WHERE {conditions} ORDER BY name LIMIT ?",
            params,
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
            self._conn.execute(
                "INSERT OR REPLACE INTO symbols (file, name, kind, start_line, end_line, signature, file_hash, file_mtime) "
                "VALUES (:file, :name, :kind, :start_line, :end_line, :signature, :file_hash, :file_mtime)",
                s,
            )
            imported += 1
        self._conn.commit()
        return imported

    @staticmethod
    def repo_key(root: Path) -> str:
        """Stable key for this repo — git remote origin URL or root path hash."""
        import hashlib, subprocess
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
