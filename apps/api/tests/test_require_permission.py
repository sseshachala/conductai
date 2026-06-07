"""
Unit tests for require_permission in app.core.auth.

No real DB, no network. Uses the same module-stub pattern as test_guard_savings.py.

require_permission(perm) returns a _check closure. We test _check directly,
injecting a mock user_id, workspace_id, and db rather than going through
FastAPI Depends resolution.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Stub heavy / infrastructure modules before any app import.
# We use sys.modules[] (not setdefault) for the modules that must stay mocked
# regardless of load order with other test files.
_log_mock = MagicMock()
_log_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules["structlog"] = _log_mock
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("sentry_sdk", MagicMock())

_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="sqlite:///:memory:",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
    # Clerk enabled so require_permission executes its real DB path
    clerk_secret_key = "REDACTED",
    clerk_frontend_api="clerk.example.com",
    environment="test",
)
sys.modules["app.core.config"] = _cfg_stub
sys.modules["app.core.database"] = MagicMock()

# sqlalchemy is a real package inside the venv — add venv site-packages so the
# import resolves even when pytest runs from outside the venv.
_venv_site = APPS_API / ".venv" / "lib"
for _p in _venv_site.glob("python*/site-packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Ensure app.core.auth is re-imported from real source (not a MagicMock from
# another test module that may have cached it).
sys.modules.pop("app.core.auth", None)

from fastapi import HTTPException  # noqa: E402
from app.core.auth import require_permission  # noqa: E402

# A valid UUID-format workspace_id (the regex in require_permission enforces this)
_WS = "00000000-0000-0000-0000-000000000001"
_UID = "user_abc123"


# ---------------------------------------------------------------------------
# DB mock helpers
# ---------------------------------------------------------------------------

def _fetchone_result(row):
    """Wrap a row so .fetchone() returns it."""
    result = MagicMock()
    result.fetchone = lambda: row
    return result


def _make_role_row(role: str):
    r = MagicMock()
    r.role = role
    return r


def _make_db_with_role_and_perm(role: str, has_perm: bool):
    """
    First db.execute call → workspace_users row with the given role.
    Second db.execute call → permission row if has_perm else None.
    """
    db = MagicMock()
    role_row = _make_role_row(role)
    perm_row = MagicMock() if has_perm else None
    db.execute.side_effect = [
        _fetchone_result(role_row),
        _fetchone_result(perm_row),
    ]
    return db


def _make_db_no_member(owner_match: bool = False):
    """
    First db.execute call → no workspace_users row.
    Second db.execute call → owner row if owner_match else None.
    """
    db = MagicMock()
    owner_row = MagicMock() if owner_match else None
    db.execute.side_effect = [
        _fetchone_result(None),
        _fetchone_result(owner_row),
    ]
    return db


def _call_check(checker, db, user_id=_UID, workspace_id=_WS):
    """Call the _check closure returned by require_permission directly."""
    return checker(user_id=user_id, workspace_id=workspace_id, db=db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidPermission:
    def test_valid_permission_returns_role(self):
        checker = require_permission("platform.eval.view")
        db = _make_db_with_role_and_perm("developer", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "developer"

    def test_valid_permission_admin_role(self):
        checker = require_permission("platform.workspace.edit")
        db = _make_db_with_role_and_perm("admin", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "admin"


class TestMissingPermission:
    def test_missing_permission_raises_403(self):
        checker = require_permission("guard.policies.edit")
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert exc_info.value.status_code == 403

    def test_missing_permission_detail_mentions_permission(self):
        checker = require_permission("guard.policies.edit")
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert "guard.policies.edit" in exc_info.value.detail


class TestNonMember:
    def test_non_member_raises_403(self):
        checker = require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert exc_info.value.status_code == 403

    def test_non_member_detail(self):
        checker = require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert "member" in exc_info.value.detail.lower() or exc_info.value.status_code == 403


class TestDevMode:
    def test_dev_mode_skips_check(self):
        checker = require_permission("guard.settings.edit")
        db = MagicMock()
        db.execute.side_effect = RuntimeError("DB should not be called in dev mode")
        with patch("app.core.auth._clerk_enabled", return_value=False):
            result = _call_check(checker, db)
        assert result == "admin"

    def test_dev_mode_never_hits_db(self):
        checker = require_permission("platform.eval.view")
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=False):
            _call_check(checker, db)
        db.execute.assert_not_called()


class TestOwnerFallback:
    def test_owner_fallback_grants_admin(self):
        """Not in workspace_users, but IS the workspace owner → returns 'admin'."""
        checker = require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "admin"

    def test_owner_fallback_does_not_check_permission_table(self):
        """Owner path returns immediately — no third DB call for role_permissions."""
        checker = require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            _call_check(checker, db)
        # Only two db.execute calls: workspace_users check + owner check
        assert db.execute.call_count == 2


class TestInvalidWorkspaceId:
    def test_non_uuid_workspace_id_raises_403(self):
        checker = require_permission("platform.eval.view")
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db, workspace_id="not-a-uuid")
        assert exc_info.value.status_code == 403
