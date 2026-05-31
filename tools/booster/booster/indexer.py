from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node, Parser

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _ST

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
    signature  TEXT NOT NULL DEFAULT ''
)
"""

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


class SymbolIndexer:
    def __init__(self, root: Path) -> None:
        self.root = root
        db_dir = root / ".booster"
        db_dir.mkdir(exist_ok=True)
        self._conn = sqlite3.connect(str(db_dir / "symbols.db"))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_CREATE_TABLE)
        self._conn.commit()
        self._py_parser = Parser(PY_LANGUAGE)
        self._ts_parser = Parser(TS_LANGUAGE)
        self._tsx_parser = Parser(TSX_LANGUAGE)

    def _parser_for(self, path: Path) -> Parser:
        if path.suffix == ".tsx" or path.suffix == ".jsx":
            return self._tsx_parser
        if path.suffix in _TS_EXTENSIONS:
            return self._ts_parser
        return self._py_parser

    def index_file(self, path: Path) -> int:
        source = path.read_bytes()
        rel = str(path.relative_to(self.root))
        self._conn.execute("DELETE FROM symbols WHERE file = ?", (rel,))
        inserted = 0

        if path.suffix in _TS_EXTENSIONS:
            parser = self._parser_for(path)
            tree = parser.parse(source)
            for name, kind, start_line, end_line, sig in _collect_ts_symbols(tree.root_node, source):
                self._conn.execute(
                    "INSERT INTO symbols (file, name, kind, start_line, end_line, signature) VALUES (?, ?, ?, ?, ?, ?)",
                    (rel, name, kind, start_line, end_line, sig),
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
                        self._conn.execute(
                            "INSERT INTO symbols (file, name, kind, start_line, end_line, signature) VALUES (?, ?, ?, ?, ?, ?)",
                            (rel, name, _PY_KIND_MAP[node.type], node.start_point[0] + 1, node.end_point[0] + 1, sig),
                        )
                        inserted += 1
                cursor.extend(node.children)

        self._conn.commit()
        return inserted

    def index_all(self, embed: bool = False) -> tuple[int, int]:
        self._conn.execute("DELETE FROM symbols")
        self._conn.commit()
        files = 0
        symbols = 0
        patterns = ["*.py", "*.ts", "*.tsx", "*.js", "*.jsx"]
        for pattern in patterns:
            for path in self.root.rglob(pattern):
                if any(part in _SKIP_DIRS for part in path.parts):
                    continue
                try:
                    symbols += self.index_file(path)
                    files += 1
                except Exception:
                    pass
        if embed:
            self.build_embeddings()
        return files, symbols

    def build_embeddings(self) -> int:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            raise SystemExit("Semantic search requires: pip install agent-booster[embed]")

        rows = self._conn.execute("SELECT id, name, signature FROM symbols ORDER BY id").fetchall()
        if not rows:
            return 0

        model: _ST = SentenceTransformer("all-MiniLM-L6-v2")
        ids = np.array([r["id"] for r in rows], dtype=np.int64)
        texts = [f"{r['name']} {r['signature']}" for r in rows]
        vecs = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
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
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return self.search(query, limit)

        from sentence_transformers import SentenceTransformer

        model: _ST = SentenceTransformer("all-MiniLM-L6-v2")
        vecs = np.load(str(vec_path))
        ids = np.load(str(ids_path))

        q = model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0]
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

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
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return _keyword_match(file_symbols, query, limit)

        file_id_set = {s["id"] for s in file_symbols}
        all_ids = np.load(str(ids_path))
        mask = np.array([int(i) in file_id_set for i in all_ids])
        if not mask.any():
            return _keyword_match(file_symbols, query, limit)

        all_vecs = np.load(str(vec_path))
        file_vecs = all_vecs[mask]
        file_ids_ordered = [int(all_ids[i]) for i in range(len(all_ids)) if mask[i]]

        model: _ST = SentenceTransformer("all-MiniLM-L6-v2")
        q = model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0]
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm

        scores = file_vecs @ q
        top_k = min(limit, len(scores))
        top_indices = np.argpartition(scores, -top_k)[-top_k:]
        top_indices = top_indices[np.argsort(scores[top_indices])[::-1]]

        id_to_sym = {s["id"]: s for s in file_symbols}
        return [id_to_sym[file_ids_ordered[i]] for i in top_indices if file_ids_ordered[i] in id_to_sym]

    def get_symbols(self, file: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM symbols WHERE file = ? ORDER BY start_line", (file,)
        ).fetchall()
        return [dict(r) for r in rows]

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
