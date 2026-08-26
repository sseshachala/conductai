"""Unit tests for app.modules.glens.tokens — mint/validate/revoke."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.glens.tokens import (
    IDLE_TIMEOUT,
    SESSION_TTL,
    TOKEN_PREFIX,
    _hash,
    validate_token,
)


def _session(**over):
    now = datetime.now(timezone.utc)
    base = dict(
        id="session-1",
        token_hash=None,
        token_revoked_at=None,
        created_at=now,
        updated_at=now,
    )
    base.update(over)
    return SimpleNamespace(**base)


def test_hash_deterministic():
    assert _hash("abc") == hashlib.sha256(b"abc").hexdigest()


def test_hash_different_inputs_produce_different_outputs():
    assert _hash("a") != _hash("b")


def test_validate_rejects_empty_token():
    db = MagicMock()
    assert validate_token(db, "") is None
    assert validate_token(db, None) is None


def test_validate_rejects_wrong_prefix():
    db = MagicMock()
    assert validate_token(db, "cond_run_abc") is None
    assert validate_token(db, "not_a_token") is None


def test_validate_returns_none_when_hash_not_found():
    db = MagicMock()
    db.query().filter().first.return_value = None
    assert validate_token(db, TOKEN_PREFIX + "abc") is None


def test_validate_returns_none_when_revoked():
    session = _session(token_revoked_at=datetime.now(timezone.utc))
    db = MagicMock()
    db.query().filter().first.return_value = session
    assert validate_token(db, TOKEN_PREFIX + "abc") is None


def test_validate_returns_none_when_idle_expired():
    old = datetime.now(timezone.utc) - IDLE_TIMEOUT - timedelta(minutes=1)
    session = _session(updated_at=old)
    db = MagicMock()
    db.query().filter().first.return_value = session
    assert validate_token(db, TOKEN_PREFIX + "abc") is None


def test_validate_returns_none_when_ttl_expired():
    old_created = datetime.now(timezone.utc) - SESSION_TTL - timedelta(hours=1)
    fresh_updated = datetime.now(timezone.utc)  # still active but session too old
    session = _session(created_at=old_created, updated_at=fresh_updated)
    db = MagicMock()
    db.query().filter().first.return_value = session
    assert validate_token(db, TOKEN_PREFIX + "abc") is None


def test_validate_returns_session_when_fresh():
    session = _session()
    db = MagicMock()
    db.query().filter().first.return_value = session
    result = validate_token(db, TOKEN_PREFIX + "abc")
    assert result is session
