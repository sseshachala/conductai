"""Call-graph (expand_calls) and test-reference (index_tests) queries."""
from __future__ import annotations

from booster.parsing import _SKIP_DIRS, _is_test_file


class GraphMixin:
    """Needs self.root and self._conn (sqlite3.Row factory)."""

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

