"""Trust validation and authentication boundaries for Okta agents."""
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.auth.federation.okta_agent import valid_config


def config(**changes):
    return {"issuer": "https://example.okta.com/oauth2/default", "audience": "api://test",
            "jwks_uri": "https://example.okta.com/oauth2/default/v1/keys",
            "status": "active", "token_profile": "okta_agent_jwt", "algorithms": ["RS256"], **changes}


@pytest.mark.parametrize("changes", [{}, {"issuer": "http://example.okta.com"},
    {"audience": ""}, {"issuer": "https://user:pass@example.okta.com"},
    {"jwks_uri": "https://unrelated.example/keys"}, {"algorithms": ["HS256"]},
    {"token_profile": "at+jwt"}, {"issuer": None}])
def test_validation(changes):
    assert valid_config(config(**changes)) == (not changes)


def test_ambiguous_workspace_denied(monkeypatch):
    from app.core.auth import _resolve_okta_jwt
    import jwt
    rows = [SimpleNamespace(workspace_id=uuid4(), config=config()) for _ in range(2)]
    monkeypatch.setattr("app.modules.auth.federation.okta_agent.candidates", lambda *_: rows)
    monkeypatch.setattr("app.modules.auth.federation.okta_agent.workspace_scope", lambda *_: nullcontext())
    monkeypatch.setattr("app.core.okta_jwt.verify_okta_jwt", lambda *a, **k: {"sub": "agent"})
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(lifecycle_state="active")
    token = jwt.encode({"iss": config()["issuer"]}, "test-only-key" * 3, algorithm="HS256")
    with pytest.raises(HTTPException, match="multiple workspaces"):
        _resolve_okta_jwt(token, db)


@pytest.mark.parametrize("status", ["disabled", "needs_review"])
def test_disabled_trust_never_verifies(monkeypatch, status):
    from app.core.auth import _resolve_okta_jwt
    import jwt
    rows = [SimpleNamespace(workspace_id=uuid4(), config=config(status=status))]
    monkeypatch.setattr("app.modules.auth.federation.okta_agent.candidates", lambda *_: rows)
    verifier = MagicMock()
    monkeypatch.setattr("app.core.okta_jwt.verify_okta_jwt", verifier)
    with pytest.raises(HTTPException) as exc:
        _resolve_okta_jwt(jwt.encode({"iss": config()["issuer"]}, "test-only-key" * 3, algorithm="HS256"), MagicMock())
    assert exc.value.status_code == 401
    verifier.assert_not_called()


def test_config_get_reads_trust_not_compatibility_columns(monkeypatch):
    from app.routers.okta_sync import get_okta_config
    db = MagicMock()
    row = SimpleNamespace(workspace_id=uuid4(), id=uuid4(), okta_issuer="old", okta_auth_enabled=False)
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr("app.routers.okta_sync._load_config", lambda *_: None)
    monkeypatch.setattr("app.modules.auth.federation.okta_agent.connection",
                        lambda *_: SimpleNamespace(config=config()))
    result = get_okta_config(str(row.workspace_id), db=db)
    assert result.issuer == config()["issuer"]
    assert result.jwt_auth_enabled is True


def test_config_put_rejects_incomplete_enabled_trust(monkeypatch):
    from app.routers.okta_sync import put_okta_config, OktaConfigPut
    db = MagicMock()
    row = SimpleNamespace(okta_issuer=None, okta_audience=None, okta_auth_enabled=False)
    db.query.return_value.filter.return_value.first.return_value = row
    monkeypatch.setattr("app.routers.okta_sync._load_config", lambda *_: None)
    with pytest.raises(HTTPException) as exc:
        put_okta_config(str(uuid4()), OktaConfigPut(jwt_auth_enabled=True), db=db)
    assert exc.value.status_code == 422
    db.commit.assert_not_called()
