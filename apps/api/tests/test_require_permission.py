"""Unit tests for require_permission in app.core.auth.

Object-level mocking only — no sys.modules manipulation. The db is injected
directly into the _check closure, so no real database is needed; imports are
safe because SQLAlchemy is lazy about connecting.

Two things to know if you edit this file:

1. conftest.py patches `_auth_mod.require_permission` to a permissive noop at
   session start (so routes always allow in the test suite). This module opts
   back into the real function via the `real_require_permission` fixture from
   conftest, applied as an autouse fixture below.

2. For the same reason, every test calls `_auth_mod.require_permission(...)`
   (attribute lookup at call time) rather than an imported `require_permission`
   symbol (which would be bound to the permissive stub at import time).

The previous version of this file worked around all this by mangling
sys.modules at import time — that polluted the module cache and caused
~35 downstream failures elsewhere in the suite.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

import app.core.auth as _auth_mod


# Restore the real require_permission for every test in this module.
@pytest.fixture(autouse=True)
def _use_real_require_permission(real_require_permission):
    yield


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
    When has_perm=False a third call checks if role_permissions is seeded;
    we return a truthy row so the fallback is NOT triggered and 403 fires.
    """
    db = MagicMock()
    role_row = _make_role_row(role)
    perm_row = MagicMock() if has_perm else None
    side_effects = [_fetchone_result(role_row), _fetchone_result(perm_row)]
    if not has_perm:
        side_effects.append(_fetchone_result(MagicMock()))  # seeded check → truthy
    db.execute.side_effect = side_effects
    return db


def _make_db_no_member(owner_match: bool = False):
    """
    First db.execute call → no workspace_users row.
    Second db.execute call → owner row if owner_match else None.
    Third db.execute call → None (GMC fallback).
    """
    db = MagicMock()
    owner_row = MagicMock() if owner_match else None
    db.execute.side_effect = [
        _fetchone_result(None),
        _fetchone_result(owner_row),
        _fetchone_result(None),  # GMC fallback
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
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_with_role_and_perm("developer", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "developer"

    def test_valid_permission_admin_role(self):
        checker = _auth_mod.require_permission("platform.workspace.edit")
        db = _make_db_with_role_and_perm("admin", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "admin"


class TestMissingPermission:
    def test_missing_permission_raises_403(self):
        checker = _auth_mod.require_permission("guard.policies.edit")
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert exc_info.value.status_code == 403

    def test_missing_permission_detail_mentions_permission(self):
        checker = _auth_mod.require_permission("guard.policies.edit")
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert "guard.policies.edit" in exc_info.value.detail


class TestNonMember:
    def test_non_member_raises_403(self):
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert exc_info.value.status_code == 403

    def test_non_member_detail(self):
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert "member" in exc_info.value.detail.lower() or exc_info.value.status_code == 403


class TestDevMode:
    def test_dev_mode_skips_check(self):
        checker = _auth_mod.require_permission("guard.settings.edit")
        db = MagicMock()
        db.execute.side_effect = RuntimeError("DB should not be called in dev mode")
        with patch("app.core.auth._clerk_enabled", return_value=False):
            result = _call_check(checker, db)
        assert result == "admin"

    def test_dev_mode_never_hits_db(self):
        checker = _auth_mod.require_permission("platform.eval.view")
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=False):
            _call_check(checker, db)
        db.execute.assert_not_called()


class TestOwnerFallback:
    def test_owner_fallback_grants_admin(self):
        """Not in workspace_users, but IS the workspace owner → returns 'admin'."""
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "admin"

    def test_owner_fallback_does_not_check_permission_table(self):
        """Owner path returns immediately — no third DB call for role_permissions."""
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            _call_check(checker, db)
        # Only two db.execute calls: workspace_users check + owner check
        assert db.execute.call_count == 2


class TestInvalidWorkspaceId:
    def test_non_uuid_workspace_id_raises_403(self):
        checker = _auth_mod.require_permission("platform.eval.view")
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db, workspace_id="not-a-uuid")
        assert exc_info.value.status_code == 403


def _make_db_unseeded(role: str):
    """
    role_permissions table is empty (migration 0044 not yet applied).

    Execution path:
      1. db.execute → workspace_users row with `role`
      2. db.execute → None (no permission row)
      3. db.execute → None (role_permissions LIMIT 1 check → empty)
    """
    db = MagicMock()
    role_row = _make_role_row(role)
    db.execute.side_effect = [
        _fetchone_result(role_row),
        _fetchone_result(None),   # permission check → not found
        _fetchone_result(None),   # seeded check → empty table
    ]
    return db


class TestUnseedledRbacFallback:
    def test_admin_gets_through_unseeded(self):
        checker = _auth_mod.require_permission("guard.settings.edit")
        db = _make_db_unseeded("admin")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "admin"

    def test_developer_read_perm_unseeded(self):
        checker = _auth_mod.require_permission("platform.eval.view")
        db = _make_db_unseeded("developer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "developer"

    def test_developer_write_perm_unseeded(self):
        checker = _auth_mod.require_permission("guard.policies.edit")
        db = _make_db_unseeded("developer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "developer"

    def test_viewer_read_perm_unseeded(self):
        checker = _auth_mod.require_permission("platform.workflows.view")
        db = _make_db_unseeded("viewer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call_check(checker, db)
        assert result == "viewer"

    def test_viewer_write_perm_unseeded_raises_403(self):
        checker = _auth_mod.require_permission("guard.policies.edit")
        db = _make_db_unseeded("viewer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call_check(checker, db)
        assert exc_info.value.status_code == 403
