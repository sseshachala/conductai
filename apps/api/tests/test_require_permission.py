"""Unit tests for check_permission in app.core.auth.

Tests target `check_permission` directly — the pure function extracted from
what used to be the `require_permission._check` closure. No FastAPI DI, no
sys.modules manipulation, no fixture acrobatics to bypass conftest's patch
of `require_permission`. The pure function doesn't touch the wrapper that
conftest patches, so tests run reliably regardless of order, autouse
fixtures, or which other tests ran first.

The db is injected directly; imports are safe because SQLAlchemy is lazy
about connecting.

See app.core.auth.require_permission for the FastAPI wrapper used by routers.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.core.auth import check_permission


# A valid UUID-format workspace_id (the regex in check_permission enforces this)
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


def _call(db, permission, user_id=_UID, workspace_id=_WS, credentials=None):
    """Call check_permission with test defaults."""
    return check_permission(
        user_id=user_id,
        workspace_id=workspace_id,
        credentials=credentials,
        db=db,
        permission=permission,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestValidPermission:
    def test_valid_permission_returns_role(self):
        db = _make_db_with_role_and_perm("developer", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "platform.eval.view")
        assert result == "developer"

    def test_valid_permission_admin_role(self):
        db = _make_db_with_role_and_perm("admin", has_perm=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "platform.workspace.edit")
        assert result == "admin"


class TestMissingPermission:
    def test_missing_permission_raises_403(self):
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "guard.policies.edit")
        assert exc_info.value.status_code == 403

    def test_missing_permission_detail_mentions_permission(self):
        db = _make_db_with_role_and_perm("developer", has_perm=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "guard.policies.edit")
        assert "guard.policies.edit" in exc_info.value.detail


class TestNonMember:
    def test_non_member_raises_403(self):
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "platform.eval.view")
        assert exc_info.value.status_code == 403

    def test_non_member_detail(self):
        db = _make_db_no_member(owner_match=False)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "platform.eval.view")
        assert "member" in exc_info.value.detail.lower() or exc_info.value.status_code == 403


class TestDevMode:
    def test_dev_mode_skips_check(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("DB should not be called in dev mode")
        with patch("app.core.auth._clerk_enabled", return_value=False):
            result = _call(db, "guard.settings.edit")
        assert result == "admin"

    def test_dev_mode_never_hits_db(self):
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=False):
            _call(db, "platform.eval.view")
        db.execute.assert_not_called()


class TestOwnerFallback:
    def test_owner_fallback_grants_admin(self):
        """Not in workspace_users, but IS the workspace owner → returns 'admin'."""
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "platform.eval.view")
        assert result == "admin"

    def test_owner_fallback_does_not_check_permission_table(self):
        """Owner path returns immediately — no third DB call for role_permissions."""
        db = _make_db_no_member(owner_match=True)
        with patch("app.core.auth._clerk_enabled", return_value=True):
            _call(db, "platform.eval.view")
        # Only two db.execute calls: workspace_users check + owner check
        assert db.execute.call_count == 2


class TestInvalidWorkspaceId:
    def test_non_uuid_workspace_id_raises_403(self):
        db = MagicMock()
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "platform.eval.view", workspace_id="not-a-uuid")
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
        db = _make_db_unseeded("admin")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "guard.settings.edit")
        assert result == "admin"

    def test_developer_read_perm_unseeded(self):
        db = _make_db_unseeded("developer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "platform.eval.view")
        assert result == "developer"

    def test_developer_write_perm_unseeded(self):
        db = _make_db_unseeded("developer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "guard.policies.edit")
        assert result == "developer"

    def test_viewer_read_perm_unseeded(self):
        db = _make_db_unseeded("viewer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = _call(db, "platform.workflows.view")
        assert result == "viewer"

    def test_viewer_write_perm_unseeded_raises_403(self):
        db = _make_db_unseeded("viewer")
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                _call(db, "guard.policies.edit")
        assert exc_info.value.status_code == 403
