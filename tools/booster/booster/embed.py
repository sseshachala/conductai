"""Embedding model + text conventions for symbol vectors."""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer as _ST

# bge is trained asymmetrically: queries get this instruction, passages get none.
# Same 384-dim output as the old all-MiniLM-L6-v2, so vectors.npy built with the
# old model would score silently wrong — EMBED_MODEL is stamped next to the vectors
# and checked before every vector search.
EMBED_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
MODEL_STAMP = "vectors_model.txt"

_embed_model: "_ST | None" = None


def get_embed_model() -> "_ST":
    global _embed_model
    if _embed_model is None:
        from sentence_transformers import SentenceTransformer
        _embed_model = SentenceTransformer(EMBED_MODEL)
    return _embed_model


def encode(texts: list[str]) -> np.ndarray:
    """Encode already-prefixed texts, L2-normalised."""
    vecs = get_embed_model().encode(texts, show_progress_bar=False, convert_to_numpy=True)
    return normalize(vecs)


def normalize(vecs: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vecs, axis=0 if vecs.ndim == 1 else 1, keepdims=vecs.ndim > 1)
    norms = np.where(norms == 0, 1.0, norms)
    return vecs / norms
