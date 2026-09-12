"""Credential issuance must consume workspace membership, never provision it."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.modules.auth import cli_token
from app.modules.auth.oauth import authorize
from app.core import auth
from fastapi import HTTPException

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
UNKNOWN_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"


def _result(row):
    value = MagicMock()
    value.fetchone.return_value = row
    return value


def _identity():
    return SimpleNamespace(
        id="33333333-3333-4333-8333-333333333333",
        workspace_id=WORKSPACE_ID,
        token_prefix="old-prefix",
        token_encrypted="old-encrypted",
        refresh_token_hash="old-hash",
        refresh_token_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )


def _assert_no_membership_writes(db):
    for call in db.execute.call_args_list:
        sql = str(call.args[0]).upper()
        assert not (
            "WORKSPACE_USERS" in sql
            and any(word in sql for word in ("INSERT", "UPDATE", "DELETE"))
        )


@pytest.mark.parametrize("workspace_id", [WORKSPACE_ID, UNKNOWN_WORKSPACE_ID, "invalid"])
def test_issuance_denies_nonmember_before_mint_or_mutation(monkeypatch, workspace_id):
    db = MagicMock()
    db.execute.return_value = _result(None)
    mint = MagicMock(side_effect=AssertionError("must authorize before minting"))
    monkeypatch.setattr(cli_token, "_mint_agent_token", mint)

    with pytest.raises(HTTPException) as exc:
        cli_token._upsert_identity(db, workspace_id, "outsider")

    assert exc.value.status_code == 403
    mint.assert_not_called()
    db.query.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
    _assert_no_membership_writes(db)


def test_existing_member_can_rotate_without_membership_writes(monkeypatch):
    db = MagicMock()
    row = _identity()
    db.execute.side_effect = [_result((1,)), _result(SimpleNamespace(id=row.id))]
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr(cli_token, "encrypt", lambda value: "encrypted-test-token")

    actual, access, refresh = cli_token._upsert_identity(db, WORKSPACE_ID, "member")

    assert actual is row
    assert access.startswith("cond_agt_")
    assert refresh.startswith("cond_ref_")
    db.commit.assert_called_once()
    _assert_no_membership_writes(db)


@pytest.mark.parametrize("linked,member,status", [(False, False, 401), (True, False, 403)])
def test_refresh_cannot_restore_removed_membership(monkeypatch, linked, member, status):
    db = MagicMock()
    row = _identity()
    before = vars(row).copy()
    db.query.return_value.filter.return_value.first.return_value = row
    db.execute.side_effect = [
        _result(SimpleNamespace(clerk_user_id="removed") if linked else None),
        _result((1,) if member else None),
    ]
    mint = MagicMock(side_effect=AssertionError("must authorize before minting"))
    monkeypatch.setattr(cli_token, "_mint_agent_token", mint)

    with pytest.raises(HTTPException) as exc:
        cli_token.rotate_identity_by_refresh("cond_ref_test", db)

    assert exc.value.status_code == status
    assert vars(row) == before
    mint.assert_not_called()
    db.commit.assert_not_called()
    _assert_no_membership_writes(db)


def test_refresh_for_current_member_rotates_without_enrollment(monkeypatch):
    db = MagicMock()
    row = _identity()
    db.query.return_value.filter.return_value.first.return_value = row
    db.execute.side_effect = [_result(SimpleNamespace(clerk_user_id="member")), _result((1,))]
    monkeypatch.setattr(cli_token, "encrypt", lambda value: "encrypted-test-token")

    actual, access, refresh = cli_token.rotate_identity_by_refresh("cond_ref_test", db)

    assert actual is row
    assert access.startswith("cond_agt_")
    assert refresh.startswith("cond_ref_")
    db.commit.assert_called_once()
    _assert_no_membership_writes(db)


def test_shared_agent_token_resolver_rejects_removed_cli_member(monkeypatch):
    token = "cond_agt_test-token"
    identity = _identity()
    identity.expires_at = None
    identity.lifecycle_state = "active"
    identity.token_type = "cli"
    identity.created_by_clerk_user_id = None
    identity.token_name = None
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [identity]
    db.execute.side_effect = [
        _result((WORKSPACE_ID, "removed")),
        _result(None),
    ]
    monkeypatch.setattr("app.core.crypto.decrypt", lambda _: {"token": token})

    assert auth.resolve_agent_token(token, db) is None


def test_dependency_agent_token_resolver_rejects_removed_cli_member(monkeypatch):
    token = "cond_agt_test-token"
    identity = _identity()
    identity.expires_at = None
    identity.lifecycle_state = "active"
    identity.token_type = "cli"
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [identity]
    db.execute.side_effect = [
        _result(SimpleNamespace(clerk_user_id="removed")),
        _result(None),
    ]
    monkeypatch.setattr("app.core.crypto.decrypt", lambda _: {"token": token})

    with pytest.raises(HTTPException) as exc:
        auth._resolve_agent_token(token, db)

    assert exc.value.status_code == 401


@pytest.mark.parametrize("workspace_id", [UNKNOWN_WORKSPACE_ID, WORKSPACE_ID])
def test_authorize_confirmation_denies_nonmember_without_issuing_code(monkeypatch, workspace_id):
    db = MagicMock()
    row = SimpleNamespace(
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        code_hash=None,
        clerk_user_id=None,
        workspace_id=None,
    )
    db.query.return_value.filter.return_value.first.return_value = row
    db.execute.return_value = _result(None)
    monkeypatch.setattr(authorize, "_verify_clerk_token", lambda _token: {"sub": "outsider"})

    with pytest.raises(HTTPException) as exc:
        authorize.confirm_authorize(
            authorize.ConfirmRequest(
                request_id="55555555-5555-4555-8555-555555555555",
                clerk_token="test-token",
                workspace_id=workspace_id,
            ),
            db,
        )

    assert exc.value.status_code == 403
    assert row.status == "pending"
    assert row.code_hash is None
    assert row.clerk_user_id is None
    assert row.workspace_id is None
    db.commit.assert_not_called()
