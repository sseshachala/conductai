"""Fail-closed deployment mode and shared authentication regression tests."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.requests import Request

from app.core import auth
from app.core.auth_deployment import validate_api_auth, validate_auth_mode
from app.core.config import Settings, settings
from app.core.console_identity import clerk_identity
from app.core.database import get_db
from app.core.stream_auth import get_user_workspace_role_sse, get_workspace_id_sse, stream_credentials

WS = "00000000-0000-0000-0000-000000000001"
OTHER = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def configured_mode(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "clerk_secret_key", "")
    monkeypatch.setattr(settings, "clerk_frontend_api", "")


def config(**kwargs):
    return SimpleNamespace(auth_mode=kwargs.get("auth_mode", "clerk"),
                           environment=kwargs.get("environment", "production"),
                           clerk_secret_key=kwargs.get("clerk_secret_key", ""),
                           clerk_frontend_api=kwargs.get("clerk_frontend_api", ""))


@pytest.mark.parametrize("mode", ["", "auto", "disabled", "CLERK"])
def test_invalid_mode_rejected(mode):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, auth_mode=mode)


@pytest.mark.parametrize("environment", ["production", "staging", "test", "Development"])
def test_development_rejected_outside_explicit_local_environments(environment):
    with pytest.raises(ValueError, match="only"):
        validate_auth_mode(config(auth_mode="development", environment=environment))


@pytest.mark.parametrize("environment", ["local", "development"])
def test_explicit_local_development_valid(environment):
    validate_api_auth(config(auth_mode="development", environment=environment))


@pytest.mark.parametrize("values", [{}, {"clerk_secret_key": "present"}, {"clerk_frontend_api": "id.example"},
                                  {"clerk_secret_key": " ", "clerk_frontend_api": "id.example"}])
def test_api_requires_complete_clerk_configuration(values):
    with pytest.raises(ValueError, match="requires"):
        validate_api_auth(config(**values))


def test_worker_mode_validation_does_not_require_clerk_credentials():
    validate_auth_mode(config())
    validate_api_auth(config(clerk_secret_key="present", clerk_frontend_api="id.example"))


def test_proxy_reserved_until_verifier_is_implemented():
    with pytest.raises(ValueError, match="not available"):
        validate_auth_mode(config(auth_mode="proxy"))


@pytest.mark.parametrize("dependency", [auth.get_user_id, auth.get_workspace_id,
                                        auth.get_guard_org_id, auth.get_guard_hook_auth])
def test_missing_clerk_is_not_development_access(dependency):
    with pytest.raises(HTTPException) as error:
        dependency()
    assert error.value.status_code == 401


def test_missing_clerk_does_not_grant_role_or_permission():
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    for call in (lambda: auth.get_user_workspace_role("outsider", WS, db),
                 lambda: auth.check_permission(user_id="outsider", workspace_id=WS, credentials=None,
                                               db=db, permission="guard.settings.edit")):
        with pytest.raises(HTTPException) as error:
            call()
        assert error.value.status_code == 403


def test_invalid_runtime_mode_cannot_enable_dev(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "development")
    with pytest.raises(HTTPException) as error:
        auth.get_user_id()
    assert error.value.status_code == 503


def test_local_credentials_still_validated(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "development")
    monkeypatch.setattr(settings, "environment", "local")
    assert auth.get_user_id() == "dev"
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid")
    monkeypatch.setattr(auth, "_resolve_okta_jwt", lambda *_: None)
    with pytest.raises(HTTPException) as error:
        auth.get_user_id(credentials, MagicMock())
    assert error.value.status_code == 401


def test_machine_auth_survives_absent_console_credentials(monkeypatch):
    agent = SimpleNamespace(workspace_id=WS, token_type="api")
    monkeypatch.setattr(auth, "_resolve_agent_token", lambda *_: (agent, None))
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="cond_api_fixture")
    assert auth.get_user_id(credential, MagicMock()) is None
    assert auth.get_workspace_id(credential, None, None, MagicMock()) == WS
    assert auth.check_permission(user_id=None, workspace_id=WS, credentials=credential,
                                 db=MagicMock(), permission="guard.settings.edit") == "admin"
    with pytest.raises(HTTPException) as error:
        auth.get_workspace_id(credential, OTHER, None, MagicMock())
    assert error.value.status_code == 403


def test_clerk_identity_normalization_and_immutable_contract():
    identity = clerk_identity({"sub": "user_test", "email": "ignored", "org_id": "org_test"}, "https://id.example")
    assert identity.user_id == "user_test" and identity.subject == "user_test"
    assert identity.provider == "clerk" and identity.organization_id == "org_test"
    with pytest.raises(AttributeError):
        identity.user_id = "other"


@pytest.mark.parametrize("claims", [None, {}, {"sub": ""}, {"sub": ["user"]}])
def test_invalid_console_subject_rejected(claims):
    with pytest.raises(HTTPException):
        clerk_identity(claims, "https://id.example")


def test_clerk_workspace_claim_still_requires_membership(monkeypatch):
    monkeypatch.setattr(auth, "_resolve_okta_jwt", lambda *_: None)
    monkeypatch.setattr(auth, "_verify_clerk_token", lambda _: {"sub": "outsider", "org_id": WS})
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None
    credential = HTTPAuthorizationCredentials(scheme="Bearer", credentials="signed-fixture")
    with pytest.raises(HTTPException) as error:
        auth.get_workspace_id(credential, None, None, db)
    assert error.value.status_code == 403


def request(query="", headers=()):
    return Request({"type": "http", "method": "GET", "path": "/", "query_string": query.encode(), "headers": headers})


def test_streams_do_not_bypass_auth_without_clerk():
    with pytest.raises(HTTPException) as error:
        get_workspace_id_sse(request(f"workspace_id={WS}"), MagicMock())
    assert error.value.status_code == 401


def test_stream_header_cannot_fall_back_to_query_token():
    credential = stream_credentials(request("token=valid", [(b"authorization", b"Basic invalid")]))
    assert credential is not None and credential.credentials == ""


def test_stream_machine_token_cannot_select_other_workspace(monkeypatch):
    monkeypatch.setattr(auth, "_resolve_agent_token", lambda *_: (SimpleNamespace(workspace_id=WS), None))
    with pytest.raises(HTTPException) as error:
        get_workspace_id_sse(request(f"token=cond_api_fixture&workspace_id={OTHER}"), MagicMock())
    assert error.value.status_code == 403


def test_stream_arbitrary_api_key_does_not_grant_admin(monkeypatch):
    monkeypatch.setattr(auth, "_resolve_okta_jwt", lambda *_: None)
    monkeypatch.setattr(auth, "_verify_clerk_token", lambda _: {"sub": "viewer"})
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = SimpleNamespace(role="viewer")
    assert get_user_workspace_role_sse(request("token=fixture&api_key=forged"), WS, db) == "viewer"


def test_stream_api_token_checks_real_scoped_permission(monkeypatch):
    agent = SimpleNamespace(workspace_id=WS, token_type="api")
    monkeypatch.setattr(auth, "_resolve_agent_token", lambda *_: (agent, None))
    assert get_user_workspace_role_sse(request("token=cond_api_fixture"), WS, MagicMock()) == "admin"


def test_guard_stream_missing_clerk_still_denies(monkeypatch):
    import asyncio
    from app.modules.guard.routers import events
    with pytest.raises(HTTPException) as error:
        asyncio.run(events.stream_events(request(f"workspace_id={WS}"), WS, None, MagicMock()))
    assert error.value.status_code == 401


def test_api_startup_rejects_missing_auth_before_background_work():
    from app.main import _startup
    with pytest.raises(ValueError, match="requires"):
        _startup()


def test_http_missing_and_spoofed_identity_denied():
    # Real auth dependencies, unlike the global permissive permission fixture.
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: MagicMock()

    @app.get("/protected")
    def protected(workspace: str = Depends(auth.get_workspace_id)):
        return {"workspace": workspace}

    with TestClient(app) as client:
        assert client.get("/protected").status_code == 401
        assert client.get("/protected", headers={"X-Auth-User": "admin", "X-Workspace-Id": WS}).status_code == 401
