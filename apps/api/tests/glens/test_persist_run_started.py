"""#1480 Gap 2 — `_persist_run_started_envelope` appends a run_started
message to the originating Lens chat session so RunBubble rehydrates on
refresh (button-click confirm path only; NL path already covered by
_extract_run_started_envelope in chat.py)."""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.glens.actor.helpers import _persist_run_started_envelope


def _row(session_id: str | None = "sess-1") -> SimpleNamespace:
    return SimpleNamespace(session_id=session_id, tool_name="run_workflow")


def _fake_db_with_session(messages: str = "[]"):
    sess = SimpleNamespace(messages=messages, id=uuid.uuid4())
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = sess
    return db, sess


def test_persists_when_row_has_session_and_result_has_run_id():
    db, sess = _fake_db_with_session()
    with patch("uuid.UUID", side_effect=lambda s: sess.id):
        _persist_run_started_envelope(
            db, _row("sess-1"),
            {"run_id": "run-abc", "workflow_name": "ship_it", "status": "pending"},
        )
    msgs = json.loads(sess.messages)
    assert len(msgs) == 1
    envelope = json.loads(msgs[0]["content"])
    assert envelope["run_started"]["run_id"] == "run-abc"
    assert envelope["run_started"]["workflow_name"] == "ship_it"
    assert envelope["run_started"]["status"] == "pending"
    db.commit.assert_called_once()


def test_noop_when_row_has_no_session_id():
    db = MagicMock()
    _persist_run_started_envelope(db, _row(session_id=None), {"run_id": "r1"})
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_noop_when_result_has_no_run_id():
    db = MagicMock()
    _persist_run_started_envelope(db, _row("sess-1"), {"status": "pending"})
    db.query.assert_not_called()
    db.commit.assert_not_called()


def test_falls_open_on_missing_session():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    # Should not raise, should not commit
    _persist_run_started_envelope(db, _row("sess-1"), {"run_id": "r1"})
    db.commit.assert_not_called()


def test_falls_open_on_exception():
    db = MagicMock()
    db.query.side_effect = RuntimeError("db exploded")
    # Must not raise — persistence is a nice-to-have
    _persist_run_started_envelope(db, _row("sess-1"), {"run_id": "r1"})
    db.rollback.assert_called_once()
