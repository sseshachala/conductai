"""Symbol search: bm25 keyword (FTS5), vector (bge), and RRF fusion of the two."""
from __future__ import annotations

import numpy as np

from booster.embed import EMBED_MODEL, MODEL_STAMP, QUERY_PREFIX, encode, normalize
from booster.parsing import split_identifier

# English filler only — words like add/get/handle are real identifiers; bm25's IDF
# already down-weights the common ones.
_STOP = {
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be",
    "we", "do", "does", "how", "where", "what", "which", "when", "it", "this", "that",
}
_NAME_WEIGHT = 5.0  # bm25 weight of the name column vs body (signature + doc)


def _fts_terms(query: str) -> list[str]:
    toks = [t for t in split_identifier(query).split() if len(t) > 1 and t not in _STOP]
    return list(dict.fromkeys(toks))


def _rrf(lists: list[list[dict]], limit: int, k: int) -> list[dict]:
    """Reciprocal Rank Fusion: score = sum over lists of 1 / (k + rank)."""
    scores: dict[int, float] = {}
    by_id: dict[int, dict] = {}
    for results in lists:
        for rank, r in enumerate(results, start=1):
            scores[r["id"]] = scores.get(r["id"], 0.0) + 1.0 / (k + rank)
            by_id.setdefault(r["id"], r)
    ranked = sorted(scores, key=scores.__getitem__, reverse=True)[:limit]
    return [by_id[sid] for sid in ranked]


class SearchMixin:
    """Needs self.root, self._conn, self._has_fts, self.get_symbols, self._daemon_embed."""

    # --- keyword ---

    def search(self, query: str, limit: int = 10, file: str | None = None) -> list[dict]:
        terms = _fts_terms(query)
        if not terms:
            return []
        where_file, params = ("AND s.file = ?", [file]) if file else ("", [])
        if self._has_fts:
            match = " OR ".join(f'"{t}"' for t in terms)
            rows = self._conn.execute(
                f"""SELECT s.* FROM symbols_fts f JOIN symbols s ON s.id = f.rowid
                     WHERE symbols_fts MATCH ? {where_file}
                     ORDER BY bm25(symbols_fts, {_NAME_WEIGHT}, 1.0) LIMIT ?""",
                [match, *params, limit],
            ).fetchall()
        else:
            # ponytail: unranked LIKE fallback for sqlite builds without FTS5.
            cond = " OR ".join("(LOWER(s.name) LIKE ? OR LOWER(s.signature) LIKE ? OR LOWER(s.doc) LIKE ?)" for _ in terms)
            like = [p for t in terms for p in (f"%{t}%",) * 3]
            rows = self._conn.execute(
                f"SELECT s.* FROM symbols s WHERE ({cond}) {where_file} ORDER BY s.name LIMIT ?",
                [*like, *params, limit],
            ).fetchall()
        return [dict(r) for r in rows]

    # --- vector ---

    def _load_vectors(self) -> tuple[np.ndarray, np.ndarray] | None:
        """(vecs, ids), or None when missing or built by a different model."""
        db = self.root / ".booster"
        try:
            if (db / MODEL_STAMP).read_text().strip() != EMBED_MODEL:
                return None
            return np.load(str(db / "vectors.npy")), np.load(str(db / "vector_ids.npy"))
        except OSError:
            return None

    def _embed_query(self, query: str) -> np.ndarray | None:
        text = f"{QUERY_PREFIX}{query}"
        vec = self._daemon_embed([text])
        if vec is not None:
            return normalize(vec[0])
        try:
            return encode([text])[0]
        except Exception:  # sentence-transformers missing or broken install
            return None

    def _vector_rank(self, query: str, limit: int, only_ids: set[int] | None = None) -> list[int] | None:
        loaded = self._load_vectors()
        if loaded is None:
            return None
        vecs, ids = loaded
        if only_ids is not None:
            mask = np.isin(ids, list(only_ids))
            vecs, ids = vecs[mask], ids[mask]
        if not len(ids):
            return []
        q = self._embed_query(query)
        if q is None:
            return None
        scores = vecs @ q
        top = np.argsort(scores)[::-1][:limit]
        return [int(ids[i]) for i in top]

    def vector_search(self, query: str, limit: int = 10) -> list[dict]:
        ranked = self._vector_rank(query, limit)
        if ranked is None:
            return self.search(query, limit)
        if not ranked:
            return []
        rows = self._conn.execute(
            f"SELECT * FROM symbols WHERE id IN ({','.join('?' * len(ranked))})", ranked
        ).fetchall()
        by_id = {r["id"]: dict(r) for r in rows}
        return [by_id[sid] for sid in ranked if sid in by_id]

    def vector_search_file(self, file: str, query: str, limit: int = 5) -> list[dict]:
        """Vector search restricted to symbols in a single file."""
        by_id = {s["id"]: s for s in self.get_symbols(file)}
        if not by_id:
            return []
        ranked = self._vector_rank(query, limit, only_ids=set(by_id))
        if ranked is None:
            return self.search(query, limit, file=file)
        return [by_id[sid] for sid in ranked if sid in by_id]

    # --- fusion ---

    def rrf_search(self, query: str, limit: int = 10, k: int = 60) -> list[dict]:
        """RRF of keyword + vector results; keyword-only when embeddings are unavailable."""
        return _rrf([self.search(query, limit * 2), self.vector_search(query, limit * 2)], limit, k)

    def rrf_search_file(self, file: str, query: str, limit: int = 5, k: int = 60) -> list[dict]:
        """RRF search restricted to symbols in a single file."""
        if not _fts_terms(query):
            return self.get_symbols(file)[:limit]  # vague task: first symbols beat nothing
        kw = self.search(query, limit * 2, file=file)
        return _rrf([kw, self.vector_search_file(file, query, limit * 2)], limit, k)
