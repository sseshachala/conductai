"""
Unit tests for the Agent Identity token consumers: MCP endpoint auth,
oauth_member_token (minting, rotation, fallback) and _token_valid (WebSocket
auth helper).

Split from ``test_agent_identity_auth.py``; shared bootstrap + stubs live in
``_agent_identity_auth_helpers.py``. No real DB, no network.
"""
from __future__ import annotations

import asyncio
import types
import uuid
from unittest.mock import MagicMock, patch

# Helpers import performs the path + env bootstrap (must precede app imports).
from tests._agent_identity_auth_helpers import (
    _AI_PATCH,
    _AgentIdentityModelStub,
    _GuardConfigStub,
    _USER_ID,
    _WS_UUID,
)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP endpoint auth (mocked HTTP layer — asyncio.run, no pytest-asyncio needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mcp_request(bearer: str | None = None):
    req = MagicMock()
    h: dict[str, str] = {}
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"

    from starlette.datastructures import Headers
    req.headers = Headers(h)

    async def _json():
        return {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}

    req.json = _json
    return req


def _mock_guard_config():
    cfg = MagicMock()
    cfg.workspace_id = _WS_UUID
    return cfg


class TestMcpEndpointAuth:
    """POST /guard/mcp — token resolution, not full integration."""

    def test_valid_cond_agt_token_returns_200_initialize(self):
        """cond_agt_* token + GuardConfig present → 200 with protocolVersion."""
        import json
        from app.modules.guard.routers.mcp import mcp_endpoint

        token = "cond_agt_" + "x" * 32
        req = _make_mcp_request(bearer=token)

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.mcp.get_clerk_user_email", return_value="user@example.com"),
            patch("app.modules.guard.routers.mcp.GuardConfig", _GuardConfigStub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = _mock_guard_config()
            mock_sl.return_value = mock_db

            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None))

        assert response.status_code == 200
        body = json.loads(response.body)
        assert "protocolVersion" in body.get("result", {})

    def test_valid_cond_api_oauth_token_returns_200(self):
        """cond_api_* OAuth token (no GMC link) + GuardConfig → 200."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        token = "cond_api_" + "y" * 32
        req = _make_mcp_request(bearer=token)

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.mcp.get_clerk_user_email", return_value="oauth@example.com"),
            patch("app.modules.guard.routers.mcp.GuardConfig", _GuardConfigStub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.modules.auth.federation.ingress.SessionLocal") as federation_sl,
            patch("app.modules.auth.federation.ingress.resolve_agent_identity_row") as caller,
        ):
            caller.return_value = types.SimpleNamespace(workspace_id=_WS_UUID, id=str(uuid.uuid4()))
            federation_db = federation_sl.return_value.__enter__.return_value
            federation_db.query.return_value.filter.return_value.first.return_value = None
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = _mock_guard_config()
            mock_sl.return_value = mock_db

            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None))

        assert response.status_code == 200

    def test_missing_token_returns_401(self):
        """No Authorization header and no query token → 401."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        req = _make_mcp_request(bearer=None)
        response = asyncio.run(mcp_endpoint(request=req, workspace_id=None))
        assert response.status_code == 401

    def test_invalid_token_returns_401(self):
        """Token that fails resolve_agent_token → 401."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        req = _make_mcp_request(bearer="garbage-token-xyz")

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=None),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None))

        assert response.status_code == 401

    def test_valid_token_no_guard_config_auto_provisions(self):
        """Token valid but workspace has no GuardConfig → auto-provision (89cc839).
        The old behavior (401 + WWW-Authenticate) caused Claude.ai OAuth re-loops
        that never converged, so first-call auto-provision replaced it."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        token = "cond_agt_" + "z" * 32
        req = _make_mcp_request(bearer=token)

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.mcp.get_clerk_user_email", return_value="user@example.com"),
            patch("app.modules.guard.routers.mcp.GuardConfig", _GuardConfigStub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.modules.guard.routers.config._get_or_create_config") as mock_get_or_create,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_sl.return_value = mock_db
            mock_get_or_create.return_value = _mock_guard_config()
            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None))

        assert response.status_code == 200
        assert mock_get_or_create.called, "missing GuardConfig should trigger auto-provision"


# ═══════════════════════════════════════════════════════════════════════════════
# oauth_member_token
# ═══════════════════════════════════════════════════════════════════════════════

def _make_oauth_request(clerk_token: str | None = None, body: dict | None = None):
    req = MagicMock()
    h: dict[str, str] = {}
    if clerk_token:
        h["Authorization"] = f"Bearer {clerk_token}"

    class _Headers(dict):
        def get(self, key, default=""):
            return super().get(key, default)

    req.headers = _Headers(h)

    async def _json():
        return body or {}

    req.json = _json
    return req


class TestOauthMemberToken:
    """POST /guard/oauth/member-token — Clerk JWT exchange for cond_api_* token."""

    def test_valid_clerk_jwt_with_workspace_id_mints_cond_api_token(self):
        """Valid Clerk JWT + workspace_id → mints a new cond_api_* token."""
        import json
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="valid.clerk.jwt",
            body={"workspace_id": str(_WS_UUID), "email": "user@example.com"},
        )

        _ai_stub = _AgentIdentityModelStub()

        with (
            patch("app.core.auth._verify_clerk_token", return_value={"sub": _USER_ID}),
            patch(_AI_PATCH, _ai_stub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.core.crypto.encrypt", return_value="encrypted-blob"),
        ):
            mock_db = MagicMock()
            mock_db.execute.return_value = MagicMock(**{"fetchone.return_value": None})
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            mock_sl.return_value = mock_db

            response = asyncio.run(oauth_member_token(req))

        assert response.status_code == 200
        body = json.loads(response.body)
        assert "member_token" in body
        assert body["member_token"].startswith("cond_api_")

    def test_valid_jwt_no_workspace_id_looks_up_from_gmc(self):
        """No workspace_id in body → looks up active workspace from GMC JOIN guard_config."""
        import json
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="valid.clerk.jwt",
            body={"email": "user@example.com"},  # no workspace_id
        )

        ws_row = MagicMock()
        ws_row.workspace_id = _WS_UUID

        _ai_stub = _AgentIdentityModelStub()

        with (
            patch("app.core.auth._verify_clerk_token", return_value={"sub": _USER_ID}),
            patch(_AI_PATCH, _ai_stub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.core.crypto.encrypt", return_value="encrypted-blob"),
        ):
            mock_db = MagicMock()
            mock_db.execute.side_effect = [
                MagicMock(**{"fetchone.return_value": ws_row}),   # workspace lookup
                MagicMock(**{"fetchone.return_value": None}),     # existing identity check
            ]
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            mock_sl.return_value = mock_db

            response = asyncio.run(oauth_member_token(req))

        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["member_token"].startswith("cond_api_")

    def test_valid_jwt_no_gmc_row_returns_404(self):
        """No GMC row for user when workspace_id not supplied → 404."""
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="valid.clerk.jwt",
            body={"email": "unknown@example.com"},
        )

        with (
            patch("app.core.auth._verify_clerk_token", return_value={"sub": "user_unknown"}),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_db.execute.return_value = MagicMock(**{"fetchone.return_value": None})
            mock_sl.return_value = mock_db

            response = asyncio.run(oauth_member_token(req))

        assert response.status_code == 404

    def test_invalid_clerk_jwt_returns_401(self):
        """_verify_clerk_token returns None → 401."""
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="bad.jwt.token",
            body={"workspace_id": str(_WS_UUID), "email": "user@example.com"},
        )

        with patch("app.core.auth._verify_clerk_token", return_value=None):
            response = asyncio.run(oauth_member_token(req))

        assert response.status_code == 401

    def test_missing_authorization_header_returns_401(self):
        """No Authorization header at all → 401 before any DB touch."""
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token=None,
            body={"workspace_id": str(_WS_UUID), "email": "user@example.com"},
        )

        response = asyncio.run(oauth_member_token(req))
        assert response.status_code == 401

    def test_re_auth_rotates_token_not_creates_new_row(self):
        """Existing cond_api_* identity → rotate prefix+encrypted, no new DB row."""
        import json
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="valid.clerk.jwt",
            body={"workspace_id": str(_WS_UUID), "email": "user@example.com"},
        )

        existing_id = str(uuid.uuid4())
        existing_row = MagicMock()
        existing_row.id = existing_id

        mock_identity = MagicMock()
        mock_identity.id = existing_id

        _ai_stub = _AgentIdentityModelStub()

        with (
            patch("app.core.auth._verify_clerk_token", return_value={"sub": _USER_ID}),
            patch(_AI_PATCH, _ai_stub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.core.crypto.encrypt", return_value="new-encrypted-blob"),
        ):
            mock_db = MagicMock()
            mock_db.execute.return_value = MagicMock(**{"fetchone.return_value": existing_row})
            mock_db.query.return_value.filter.return_value.first.return_value = mock_identity
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            mock_sl.return_value = mock_db

            response = asyncio.run(oauth_member_token(req))

        # db.add() must NOT have been called (rotation, not creation)
        mock_db.add.assert_not_called()
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["member_token"].startswith("cond_api_")
        assert mock_identity.token_encrypted == "new-encrypted-blob"

    def test_oauth_mint_does_not_update_guard_member_config_agent_identity_id(self):
        """New OAuth identity must NOT set GMC.agent_identity_id (ponytail contract)."""
        from app.modules.guard.routers.mcp import oauth_member_token

        req = _make_oauth_request(
            clerk_token="valid.clerk.jwt",
            body={"workspace_id": str(_WS_UUID), "email": "user@example.com"},
        )

        _ai_stub = _AgentIdentityModelStub()

        with (
            patch("app.core.auth._verify_clerk_token", return_value={"sub": _USER_ID}),
            patch(_AI_PATCH, _ai_stub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
            patch("app.core.crypto.encrypt", return_value="encrypted-blob"),
        ):
            mock_db = MagicMock()
            mock_db.execute.return_value = MagicMock(**{"fetchone.return_value": None})
            mock_db.add = MagicMock()
            mock_db.commit = MagicMock()
            mock_sl.return_value = mock_db

            asyncio.run(oauth_member_token(req))

        # Verify no execute() call writes agent_identity_id to guard_member_config
        for c in mock_db.execute.call_args_list:
            sql_arg = str(c.args[0] if c.args else "")
            if "agent_identity_id" in sql_arg.lower():
                # Only SELECTs are permitted, never an UPDATE/INSERT
                assert "SELECT" in sql_arg.upper(), (
                    "oauth_member_token must not write agent_identity_id to guard_member_config"
                )


# ═══════════════════════════════════════════════════════════════════════════════
# _token_valid (WebSocket auth helper)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenValid:
    """_token_valid is synchronous and wraps resolve_agent_token for the WS layer."""

    def test_valid_token_returns_true(self):
        from app.modules.guard.routers.ws import _token_valid

        with (
            patch("app.modules.guard.routers.ws.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            result = _token_valid("cond_agt_validtoken1234567890")

        assert result is True

    def test_invalid_token_returns_false(self):
        from app.modules.guard.routers.ws import _token_valid

        with (
            patch("app.modules.guard.routers.ws.resolve_agent_token", return_value=None),
            patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            result = _token_valid("garbage")

        assert result is False

    def test_empty_token_returns_false_without_db_call(self):
        """Empty string short-circuits before DB is opened."""
        from app.modules.guard.routers.ws import _token_valid

        with patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl:
            result = _token_valid("")

        mock_sl.assert_not_called()
        assert result is False

    def test_db_exception_returns_false_never_raises(self):
        """Exception in resolve_agent_token is swallowed → False (fail-closed)."""
        from app.modules.guard.routers.ws import _token_valid

        with (
            patch("app.modules.guard.routers.ws.resolve_agent_token", side_effect=RuntimeError("db gone")),
            patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            result = _token_valid("cond_agt_something")

        assert result is False

    def test_session_always_closed_on_valid_path(self):
        """DB session is closed even on success (no resource leak)."""
        from app.modules.guard.routers.ws import _token_valid

        with (
            patch("app.modules.guard.routers.ws.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            _token_valid("cond_agt_something1234567890abc")

        mock_db.close.assert_called_once()

    def test_session_always_closed_on_exception_path(self):
        """DB session is closed even when resolve_agent_token raises."""
        from app.modules.guard.routers.ws import _token_valid

        with (
            patch("app.modules.guard.routers.ws.resolve_agent_token", side_effect=Exception("boom")),
            patch("app.modules.guard.routers.ws.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_sl.return_value = mock_db
            _token_valid("cond_agt_something1234567890abc")

        mock_db.close.assert_called_once()

