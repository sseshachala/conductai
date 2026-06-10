"""
Tests for agent memory write/read path after the vector(1536) column upgrade.

Verifies:
  1. Write stores a list[float] on AgentMemory.embedding (not a JSON string).
  2. Read issues SQL without the ::vector cast and passes a stringified vector.
  3. Dimension mismatch (e.g. 512d Voyage client) skips embedding and falls back.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from app.runtime.executor import _execute_memory_inner


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FAKE_DIMS = 1536
FAKE_VEC = [0.1] * FAKE_DIMS


class FakeEmbeddingClient:
    """Minimal embedding client that returns a fixed 1536d vector."""
    dimensions = FAKE_DIMS

    def embed(self, text: str) -> list[float]:
        return FAKE_VEC


class FakeEmbeddingClient512:
    """Simulates Voyage: 512d — should be rejected by the executor."""
    dimensions = 512

    def embed(self, text: str) -> list[float]:
        return [0.1] * 512


def _write_block(summary: str = "agent learned that X causes Y") -> dict:
    return {"data": {"config": {"action": "write", "scope": "repo", "key": "owner/repo", "summary": summary}}}


def _read_block(key: str = "owner/repo") -> dict:
    return {"data": {"config": {"action": "read", "scope": "repo", "key": key, "limit": 3}}}


def _make_db(rows=None):
    """Return a mock DB session whose add/commit do nothing."""
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    # For the read path, fetchall() returns provided rows
    if rows is not None:
        db.execute.return_value.fetchall.return_value = rows
    return db


WS_ID = str(uuid.uuid4())
PLAYBOOK = "pr-reviewer"
RUN_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Write tests
# ---------------------------------------------------------------------------

def test_write_stores_list_not_json_string():
    """embedding must be a list[float], not json.dumps output."""
    db = _make_db()
    state = {}

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=FakeEmbeddingClient()):
        _execute_memory_inner(_write_block(), state, db, RUN_ID, WS_ID, PLAYBOOK)

    db.add.assert_called_once()
    row = db.add.call_args[0][0]

    assert isinstance(row.embedding, list), "embedding should be list[float], not str"
    assert len(row.embedding) == FAKE_DIMS
    assert row.embedding == FAKE_VEC


def test_write_no_embedding_when_no_client():
    """If no embedding client is available, embedding must be None (recency fallback)."""
    db = _make_db()

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=None):
        result = _execute_memory_inner(_write_block(), {}, db, RUN_ID, WS_ID, PLAYBOOK)

    row = db.add.call_args[0][0]
    assert row.embedding is None
    assert result["written"] is True


def test_write_dimension_mismatch_skips_embedding():
    """512d Voyage client must not write to the 1536d column — embedding stays None."""
    db = _make_db()

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=FakeEmbeddingClient512()):
        result = _execute_memory_inner(_write_block(), {}, db, RUN_ID, WS_ID, PLAYBOOK)

    row = db.add.call_args[0][0]
    assert row.embedding is None
    assert result["written"] is True


# ---------------------------------------------------------------------------
# Read tests
# ---------------------------------------------------------------------------

def test_read_sql_has_no_vector_cast():
    """The SQL issued for vector search must NOT contain ::vector cast on the column."""
    db = _make_db(rows=[])

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=FakeEmbeddingClient()):
        _execute_memory_inner(_read_block(), {}, db, RUN_ID, WS_ID, PLAYBOOK)

    db.execute.assert_called_once()
    sql_text = str(db.execute.call_args[0][0])
    assert "embedding::vector" not in sql_text, "native vector column must not be cast — HNSW won't fire"


def test_read_passes_stringified_vector():
    """The :vec param must be a string representation, not a json.dumps list."""
    db = _make_db(rows=[])

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=FakeEmbeddingClient()):
        _execute_memory_inner(_read_block(), {}, db, RUN_ID, WS_ID, PLAYBOOK)

    _, kwargs = db.execute.call_args
    vec_param = kwargs.get("vec") or db.execute.call_args[0][1].get("vec")
    # str([0.1, 0.1, ...]) starts with '[' — not json.dumps which also starts with '['
    # but we specifically confirm it's NOT a bytes object or raw list
    assert isinstance(vec_param, str)


def test_read_falls_back_to_recency_on_dimension_mismatch():
    """512d Voyage client must fall back to ORM recency query, not vector search."""
    db = _make_db()
    db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    with patch("app.runtime.embedding_client.create_embedding_client", return_value=FakeEmbeddingClient512()):
        result = _execute_memory_inner(_read_block(), {}, db, RUN_ID, WS_ID, PLAYBOOK)

    db.execute.assert_not_called()  # vector SQL must not be issued
    db.query.assert_called_once()
    assert result["entries"] == []
