"""Real PostgreSQL regressions for concurrent CLI/MCP credentials.

Set CREDENTIAL_TEST_DATABASE_URL to a disposable local database. Each test
creates and drops its own random schema; no existing application rows are used.
"""
import importlib.util
import base64
import hashlib
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core import auth
from app.core.crypto import encrypt
from app.modules.agent_identity.credentials import token_hash
from app.modules.agent_identity.models import AgentCredentialSession, AgentIdentity
from app.modules.auth.cli_token import _upsert_identity, rotate_identity_by_refresh
from app.models.oauth import OauthAuthCode, OauthClient

WS = "11111111-1111-4111-8111-111111111111"
USER = "credential-session-test"


@pytest.fixture
def database():
    url = os.environ.get("CREDENTIAL_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CREDENTIAL_TEST_DATABASE_URL not set")
    schema = "credential_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY, owner_id text)"))
            connection.execute(text("CREATE TABLE workspace_users (workspace_id uuid, clerk_user_id text)"))
            AgentIdentity.__table__.create(connection)
            OauthClient.__table__.create(connection)
            OauthAuthCode.__table__.create(connection)
            connection.execute(text("""CREATE TABLE guard_member_config (
                workspace_id uuid, clerk_user_id text, member_token text,
                agent_identity_id varchar(36) REFERENCES agent_identities(id),
                active boolean, joined_at timestamptz,
                UNIQUE (workspace_id, clerk_user_id))"""))
            path = Path(__file__).resolve().parents[1] / "alembic/versions/0128_agent_credential_sessions.py"
            spec = importlib.util.spec_from_file_location("session_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            connection.execute(text("INSERT INTO workspaces VALUES (:ws, 'another-owner')"), {"ws": WS})
            connection.execute(text("INSERT INTO workspace_users VALUES (:ws, :user)"), {"ws": WS, "user": USER})
        yield engine
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                migration.downgrade()
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def issue(db):
    return _upsert_identity(db, WS, USER)


def assert_access(db, token, identity_id):
    assert auth.resolve_agent_token(token, db) == (WS, USER)
    assert auth._resolve_agent_token(token, db)[0].id == identity_id
    assert auth.resolve_agent_identity_row(token, db).id == identity_id
    assert not auth.token_is_expired(token, db)


def assert_denied(db, access, refresh):
    assert auth.resolve_agent_token(access, db) is None
    assert auth.resolve_agent_identity_row(access, db) is None
    with pytest.raises(HTTPException) as error:
        auth._resolve_agent_token(access, db)
    assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        rotate_identity_by_refresh(refresh, db)
    assert error.value.status_code in (401, 403)
    db.rollback()


def test_second_login_and_refresh_preserve_first_identity_and_other_client(database):
    with Session(database) as db:
        first, access_a, refresh_a = issue(db)
        identity_id = first.id
        second, access_b, refresh_b = issue(db)
        assert second.id == identity_id
        assert access_a != access_b and refresh_a != refresh_b
        assert db.query(AgentIdentity).count() == 1
        assert db.query(AgentCredentialSession).count() == 2
        assert_access(db, access_a, identity_id)
        assert_access(db, access_b, identity_id)
        _, next_a, next_refresh_a = rotate_identity_by_refresh(refresh_a, db)
        assert_access(db, next_a, identity_id)
        assert_access(db, access_b, identity_id)
        assert_denied(db, access_a, refresh_a)
        _, next_b, _ = rotate_identity_by_refresh(refresh_b, db)
        assert_access(db, next_a, identity_id)
        assert_access(db, next_b, identity_id)
        assert next_refresh_a != refresh_a


@pytest.mark.parametrize("change", ["membership", "inactive_member", "deactivated", "expired", "revoked"])
def test_revocation_still_denies_access_and_refresh(database, change):
    with Session(database) as db:
        identity, access, refresh = issue(db)
        if change == "membership":
            db.execute(text("DELETE FROM workspace_users"))
        elif change == "inactive_member":
            db.execute(text("UPDATE guard_member_config SET active = false"))
        elif change in ("deactivated", "expired"):
            identity.lifecycle_state = change
        else:
            db.query(AgentCredentialSession).update({"revoked_at": datetime.now(timezone.utc)})
        db.commit()
        assert_denied(db, access, refresh)


def test_expired_access_can_refresh_but_expired_refresh_cannot(database):
    with Session(database) as db:
        identity, access, refresh = issue(db)
        identity_id = identity.id
        db.query(AgentCredentialSession).update({"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)})
        db.commit()
        assert auth.resolve_agent_token(access, db) is None
        assert auth.token_is_expired(access, db)
        _, access, refresh = rotate_identity_by_refresh(refresh, db)
        assert_access(db, access, identity_id)
        db.query(AgentCredentialSession).update({
            "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
            "refresh_token_expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        })
        db.commit()
        assert_denied(db, access, refresh)


def test_valid_legacy_refresh_upgrades_without_invalidating_another_session(database):
    with Session(database) as db:
        identity, session_access, session_refresh = issue(db)
        identity_id = identity.id
        old_access = "cond_agt_" + "a" * 64
        old_refresh = "cond_ref_" + "b" * 64
        identity.token_prefix = old_access[:13]
        identity.token_encrypted = encrypt({"token": old_access})
        identity.refresh_token_hash = token_hash(old_refresh)
        identity.refresh_token_expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        db.commit()
        assert_access(db, old_access, identity_id)
        _, upgraded_access, _ = rotate_identity_by_refresh(old_refresh, db)
        assert_access(db, upgraded_access, identity_id)
        assert_access(db, session_access, identity_id)
        assert_denied(db, old_access, old_refresh)
        rotate_identity_by_refresh(session_refresh, db)


def test_concurrent_refresh_accepts_exactly_one_use(database):
    with Session(database) as db:
        _, _, refresh = issue(db)
    barrier = Barrier(2)

    def rotate():
        with Session(database) as db:
            barrier.wait(timeout=10)
            try:
                rotate_identity_by_refresh(refresh, db)
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: rotate(), range(2)))
    assert sorted(results) == [200, 401]


def test_concurrent_first_logins_share_identity_not_credentials(database):
    barrier = Barrier(2)

    def login():
        with Session(database) as db:
            barrier.wait(timeout=10)
            identity, access, _ = issue(db)
            return identity.id, access

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: login(), range(2)))
    assert a[0] == b[0]
    assert a[1] != b[1]
    with Session(database) as db:
        assert_access(db, a[1], a[0])
        assert_access(db, b[1], b[0])


def test_cli_exchange_then_mcp_authorization_preserves_both_clients(database, monkeypatch):
    from app.modules.auth.oauth.grants import authorization_code, refresh_token, token_exchange

    monkeypatch.setattr(token_exchange, "_verify_clerk_token", lambda _: {"sub": USER})
    with Session(database) as db:
        cli = token_exchange.handle("synthetic-jwt", "urn:ietf:params:oauth:token-type:jwt", WS, db)
        identity_id = auth.resolve_agent_identity_row(cli["access_token"], db).id
        verifier = "synthetic-pkce-verifier-" + "x" * 32
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        callback = "http://localhost:23514/oauth/callback"
        db.add(OauthClient(client_id="synthetic-mcp-client", client_name="Test MCP", redirect_uris=[callback]))
        db.flush()
        db.add(OauthAuthCode(
            id=uuid.uuid4(), code_hash=token_hash("synthetic-code"),
            client_id="synthetic-mcp-client", redirect_uri=callback,
            code_challenge=challenge, code_challenge_method="S256", state="synthetic-state",
            clerk_user_id=USER, workspace_id=uuid.UUID(WS), status="issued",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        ))
        db.commit()
        mcp = authorization_code.handle("synthetic-code", verifier, "synthetic-mcp-client", callback, db)
        assert_access(db, cli["access_token"], identity_id)
        assert_access(db, mcp["access_token"], identity_id)
        rotated_cli = refresh_token.handle(cli["refresh_token"], db)
        assert_access(db, rotated_cli["access_token"], identity_id)
        assert_access(db, mcp["access_token"], identity_id)
        rotated_mcp = refresh_token.handle(mcp["refresh_token"], db)
        assert_access(db, rotated_cli["access_token"], identity_id)
        assert_access(db, rotated_mcp["access_token"], identity_id)


def test_admin_regeneration_revokes_all_sessions(database):
    from app.modules.agent_identity.router import regenerate_agent_identity

    with Session(database) as db:
        identity, access_a, refresh_a = issue(db)
        _, access_b, refresh_b = issue(db)
        regenerate_agent_identity(WS, identity.id, _ws=WS, _="admin", db=db)
        assert_denied(db, access_a, refresh_a)
        assert_denied(db, access_b, refresh_b)


@pytest.mark.parametrize("bearer", [True, False])
def test_install_status_does_not_replace_identity_with_expired_legacy_snapshot(database, monkeypatch, bearer):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from starlette.requests import Request
    from app.modules.guard.routers.config import get_install_status, GuardConfig, Workspace

    monkeypatch.setattr(auth, "get_clerk_user_email", lambda _: "synthetic@example.test")
    with Session(database) as db:
        identity, access, refresh = issue(db)
        identity_id = identity.id
        identity.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        db.commit()
        query = db.query

        def metadata_query(model):
            if model is Workspace:
                result = Mock()
                result.filter.return_value.first.return_value = SimpleNamespace(org_id=None, owner_id=None)
                return result
            if model is GuardConfig:
                result = Mock()
                result.filter.return_value.first.return_value = SimpleNamespace(invite_code="synthetic")
                return result
            return query(model)

        monkeypatch.setattr(db, "query", metadata_query)
        request = Request({"type": "http", "headers": [
            (b"authorization", ("Bearer " + (access if bearer else "synthetic-clerk-jwt")).encode()),
        ]})
        installed = get_install_status(request=request, db=db, workspace_id=WS, user_id=USER)
        assert installed.installed
        assert installed.agent_token == (access if bearer else None)
        assert query(AgentIdentity).count() == 1
        assert_access(db, access, identity_id)
        rotate_identity_by_refresh(refresh, db)


def test_session_list_redacts_credentials_and_revoke_affects_only_one_login(database):
    from starlette.requests import Request
    from app.modules.agent_identity.router import list_credential_sessions, revoke_credential_session

    with Session(database) as db:
        identity, access_a, refresh_a = issue(db)
        identity_id = identity.id
        _, access_b, _ = issue(db)
        request = Request({"type": "http", "headers": [(b"authorization", f"Bearer {access_a}".encode())]})
        result = list_credential_sessions(WS, identity_id, request, limit=1, offset=0, db=db)
        assert result.has_more
        assert len(result.sessions) == 1
        all_sessions = list_credential_sessions(WS, identity_id, request, limit=50, offset=0, db=db)
        current = next(row for row in all_sessions.sessions if row.is_current)
        assert set(current.model_dump()) == {
            "id", "created_at", "expires_at", "refresh_token_expires_at", "revoked_at", "status", "is_current",
        }
        for secret in (access_a, access_b, refresh_a, token_hash(access_a), token_hash(refresh_a)):
            assert secret not in all_sessions.model_dump_json()
        revoked = revoke_credential_session(WS, identity_id, current.id, request, db=db)
        assert revoked.status == "revoked"
        repeated = revoke_credential_session(WS, identity_id, current.id, request, db=db)
        assert repeated.revoked_at == revoked.revoked_at
        assert_denied(db, access_a, refresh_a)
        assert_access(db, access_b, identity_id)


@pytest.mark.parametrize("state", ["active", "refreshable", "expired", "blocked"])
def test_session_list_displays_effective_status(database, state):
    from starlette.requests import Request
    from app.modules.agent_identity.router import list_credential_sessions

    with Session(database) as db:
        identity, _, _ = issue(db)
        session = db.query(AgentCredentialSession).first()
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        if state == "refreshable":
            session.expires_at = past
        elif state == "expired":
            session.expires_at = past
            session.refresh_token_expires_at = past
        elif state == "blocked":
            db.execute(text("DELETE FROM workspace_users"))
        db.commit()
        result = list_credential_sessions(WS, identity.id, Request({"type": "http", "headers": []}), limit=50, offset=0, db=db)
        assert result.sessions[0].status == state


def test_session_endpoints_reject_other_identity_and_workspace(database):
    from starlette.requests import Request
    from app.modules.agent_identity.router import list_credential_sessions, revoke_credential_session

    with Session(database) as db:
        identity, _, _ = issue(db)
        session = db.query(AgentCredentialSession).first()
        request = Request({"type": "http", "headers": []})
        other = "22222222-2222-4222-8222-222222222222"
        for ws, aid, sid in [(other, identity.id, session.id), (WS, other, session.id), (WS, identity.id, other)]:
            with pytest.raises(HTTPException) as error:
                revoke_credential_session(ws, aid, sid, request, db=db)
            assert error.value.status_code == 404
        with pytest.raises(HTTPException) as error:
            list_credential_sessions(other, identity.id, request, limit=50, offset=0, db=db)
        assert error.value.status_code == 404
        db.refresh(session)
        assert session.revoked_at is None
