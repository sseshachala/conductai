"""Validate POST /glens/chat/feedback — verdict validation, upsert semantics,
workspace scoping. Backed by mocked SQLAlchemy sessions so tests don't
require Postgres.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.modules.glens.routers.chat import FeedbackIn, submit_feedback


_WS = "00000000-0000-0000-0000-000000000000"
_SESSION = "11111111-1111-1111-1111-111111111111"
_USER = "user_test_123"


def _mock_session_ok():
    """A DB mock where the target GlensChatSession exists in the workspace."""
    session_row = MagicMock()
    session_row.id = uuid.UUID(_SESSION)
    session_row.workspace_id = uuid.UUID(_WS)

    class _Q:
        def __init__(self, first_val):
            self._first = first_val
        def filter(self, *_a, **_k): return self
        def first(self): return self._first

    db = MagicMock()
    # First query() call → returns the session lookup. Second → existing
    # feedback lookup (None so we hit the "create" branch by default).
    db.query.side_effect = [_Q(session_row), _Q(None)]
    return db


def test_submit_feedback_rejects_invalid_verdict():
    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="maybe")
    with pytest.raises(HTTPException) as exc:
        submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=MagicMock())
    assert exc.value.status_code == 400
    assert "verdict" in exc.value.detail.lower()


def test_submit_feedback_rejects_empty_message_id():
    req = FeedbackIn(session_id=_SESSION, message_id="   ", verdict="up")
    with pytest.raises(HTTPException) as exc:
        submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=MagicMock())
    assert exc.value.status_code == 400
    assert "message_id" in exc.value.detail.lower()


def test_submit_feedback_rejects_bad_session_uuid():
    req = FeedbackIn(session_id="not-a-uuid", message_id="msg-1", verdict="up")
    with pytest.raises(HTTPException) as exc:
        submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=MagicMock())
    assert exc.value.status_code == 400
    assert "session_id" in exc.value.detail.lower()


def test_submit_feedback_rejects_long_comment():
    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="down", comment="x" * 2001)
    with pytest.raises(HTTPException) as exc:
        submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=MagicMock())
    assert exc.value.status_code == 400


def test_submit_feedback_404_when_session_not_in_workspace():
    class _Q:
        def filter(self, *_a, **_k): return self
        def first(self): return None
    db = MagicMock()
    db.query.return_value = _Q()

    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="up")
    with pytest.raises(HTTPException) as exc:
        submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=db)
    assert exc.value.status_code == 404


def test_submit_feedback_created_when_no_prior():
    db = _mock_session_ok()
    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="up")

    out = submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=db)

    assert out == {"ok": True, "action": "created", "verdict": "up"}
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.verdict == "up"
    assert added.message_id == "msg-1"
    assert added.clerk_user_id == _USER
    db.commit.assert_called_once()


def test_submit_feedback_updated_when_prior_exists():
    """User flips their vote from up → down; existing row's verdict + comment
    get overwritten, no new row inserted."""
    session_row = MagicMock()
    session_row.id = uuid.UUID(_SESSION)

    existing = MagicMock()
    existing.verdict = "up"
    existing.comment = None

    class _Q:
        def __init__(self, first_val): self._first = first_val
        def filter(self, *_a, **_k): return self
        def first(self): return self._first

    db = MagicMock()
    db.query.side_effect = [_Q(session_row), _Q(existing)]

    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="down", comment="unhelpful")
    out = submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=db)

    assert out == {"ok": True, "action": "updated", "verdict": "down"}
    assert existing.verdict == "down"
    assert existing.comment == "unhelpful"
    db.add.assert_not_called()
    db.commit.assert_called_once()


def test_submit_feedback_accepts_comment_on_down():
    db = _mock_session_ok()
    req = FeedbackIn(session_id=_SESSION, message_id="msg-1", verdict="down", comment="wrong data")

    out = submit_feedback(req, _="ok", workspace_id=_WS, user_id=_USER, db=db)

    assert out["action"] == "created"
    assert out["verdict"] == "down"
    added = db.add.call_args.args[0]
    assert added.comment == "wrong data"
