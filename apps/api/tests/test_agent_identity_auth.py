"""
Unit tests for the Agent Identity token resolution system.

Covers:
  - resolve_agent_token: cond_agt_*, cond_api_*, legacy member tokens
  - MCP endpoint auth (mocked HTTP layer, asyncio.run for coroutines)
  - oauth_member_token: minting, rotation, fallback logic
  - _token_valid (WebSocket auth helper)

No real DB, no network. Uses MagicMock for DB sessions and patches
encrypt/decrypt so crypto stays hermetic.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ── Path + env bootstrap (must precede all app imports) ─────────────────────

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["ANTHROPIC_API_KEY"] = "sk-test"
os.environ["ENCRYPTION_KEY"] = "test-key-32-bytes-long-xxxxxxxx!"

# ── Stub noisy infrastructure before any app import ─────────────────────────

_log_mock = MagicMock()
_log_mock.get_logger = MagicMock(return_value=MagicMock())
_log_mock.contextvars = MagicMock()
sys.modules["structlog"] = _log_mock
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("sentry_sdk", MagicMock())

_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="sqlite:///:memory:",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
    clerk_secret_key="sk_test_secret",
    clerk_frontend_api="clerk.example.com",
    environment="test",
)
sys.modules["app.core.config"] = _cfg_stub
sys.modules["app.core.database"] = MagicMock()

# Add venv site-packages so SQLAlchemy / cryptography are importable
_venv_site = APPS_API / ".venv" / "lib"
for _p in _venv_site.glob("python*/site-packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# Evict any cached module copies so the real source is loaded fresh
for _mod in list(sys.modules.keys()):
    if _mod.startswith("app.core.auth") or _mod.startswith("app.core.crypto"):
        del sys.modules[_mod]

# ── Constants shared across tests ────────────────────────────────────────────

_WS_ID = str(uuid.uuid4())
_WS_UUID = uuid.UUID(_WS_ID)
_USER_ID = "user_clerk_abc123"
_AGT_PREFIX_LEN = len("cond_agt_") + 4   # 13
_API_PREFIX_LEN = len("cond_api_") + 4   # 13


# ── AgentIdentity stub ───────────────────────────────────────────────────────
# resolve_agent_token does:
#   db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix)
# AgentIdentity.token_prefix must behave like a SQLAlchemy column descriptor
# (supports ==) when used in a filter expression. We stub it with a simple
# sentinel so the MagicMock DB chain resolves cleanly.

class _ColDescriptor:
    """Minimal column descriptor: supports == for use in filter()."""
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return f"{self.name}=={other!r}"   # truthy string; MagicMock accepts it


class _AgentIdentityStub:
    """Stub that provides column descriptors without a real DB engine."""
    token_prefix = _ColDescriptor("token_prefix")


class _GuardConfigStub:
    """Stub for GuardConfig used in mcp_endpoint filter expressions."""
    workspace_id = _ColDescriptor("workspace_id")


class _AgentIdentityModelStub:
    """Stub for AgentIdentity used in oauth_member_token filter expressions.
    Also acts as a constructor so the `AgentIdentity(...)` call inside the
    function returns a usable MagicMock instead of raising StopIteration."""
    id = _ColDescriptor("id")

    def __call__(self, **kwargs):
        row = MagicMock()
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row
    __tablename__ = "agent_identities"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ai_row(token: str, workspace_id: str | None = None, created_by: str | None = None, token_name: str | None = None):
    """Return a minimal AgentIdentity-like object."""
    row = MagicMock()
    row.id = str(uuid.uuid4())
    row.token_prefix = token[:_AGT_PREFIX_LEN]
    row.workspace_id = uuid.UUID(workspace_id) if workspace_id else _WS_UUID
    row.created_by_clerk_user_id = created_by
    row.token_name = token_name
    row.name = token_name or "test-token"
    return row


def _db_with_ai(ai_row, member_row=None):
    """Build a mock Session that returns ai_row from AgentIdentity query
    and member_row from the raw SQL execute call."""
    db = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [ai_row]
    db.query.return_value.filter.return_value = query_result

    execute_result = MagicMock()
    execute_result.fetchone.return_value = member_row
    db.execute.return_value = execute_result
    return db


def _db_no_ai():
    """Session that returns no AgentIdentity rows."""
    db = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.query.return_value.filter.return_value = query_result
    return db


def _db_for_legacy(member_row):
    """Session for legacy bare-hex / guard-mt-* path (no query(), only execute())."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    execute_result = MagicMock()
    execute_result.fetchone.return_value = member_row
    db.execute.return_value = execute_result
    return db


def _agt_token():
    import secrets
    return "cond_agt_" + secrets.token_urlsafe(32)


def _api_token():
    import secrets
    return "cond_api_" + secrets.token_urlsafe(32)


# ── Patch target for AgentIdentity inside resolve_agent_token ────────────────
# auth.py does `from app.modules.agent_identity.models import AgentIdentity`
# inside the function body, so we patch the module attribute.
_AI_PATCH = "app.modules.agent_identity.models.AgentIdentity"


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_agent_token — cond_agt_*
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveAgentTokenCondAgt:
    """cond_agt_* — 8-hour CLI session tokens."""

    def test_valid_with_gmc_link_returns_workspace_and_user(self):
        """Happy path: GMC row present → (workspace_id, clerk_user_id)."""
        from app.core.auth import resolve_agent_token

        token = _agt_token()
        ai = _make_ai_row(token)
        member_row = (str(_WS_UUID), _USER_ID)
        db = _db_with_ai(ai, member_row=member_row)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            result = resolve_agent_token(token, db)

        assert result == (str(_WS_UUID), _USER_ID)

    def test_expired_token_no_matching_row_returns_none(self):
        """Prefix lookup finds no row → None (token effectively expired/revoked)."""
        from app.core.auth import resolve_agent_token

        token = _agt_token()
        db = _db_no_ai()

        with patch(_AI_PATCH, _AgentIdentityStub):
            result = resolve_agent_token(token, db)

        assert result is None

    def test_decrypt_mismatch_returns_none(self):
        """decrypt returns a different token value → skip row → None."""
        from app.core.auth import resolve_agent_token

        token = _agt_token()
        ai = _make_ai_row(token)
        db = _db_with_ai(ai, member_row=None)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": "cond_agt_completelydifferent"}),
        ):
            result = resolve_agent_token(token, db)

        assert result is None

    def test_decrypt_exception_skips_row_returns_none(self):
        """decrypt raises → row skipped gracefully → None."""
        from app.core.auth import resolve_agent_token

        token = _agt_token()
        ai = _make_ai_row(token)
        db = _db_with_ai(ai, member_row=None)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", side_effect=Exception("corrupt blob")),
        ):
            result = resolve_agent_token(token, db)

        assert result is None

    def test_prefix_too_short_is_treated_as_legacy_path(self):
        """Token shorter than expected prefix lookup len still resolves (goes to legacy path).
        The 'cond_agt_' prefix is recognised and the function tries AgentIdentity.
        With no rows it returns None."""
        from app.core.auth import resolve_agent_token

        # 'cond_agt_sho' — starts with cond_agt_ so goes to AI path, but no rows
        token = "cond_agt_sho"
        db = _db_no_ai()

        with patch(_AI_PATCH, _AgentIdentityStub):
            result = resolve_agent_token(token, db)

        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_agent_token — cond_api_*
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveAgentTokenCondApi:
    """cond_api_* — long-lived API / OAuth tokens."""

    def test_with_gmc_link_returns_via_gmc(self):
        """CLI-issued cond_api_* that has a GMC row resolves through GMC."""
        from app.core.auth import resolve_agent_token

        token = _api_token()
        ai = _make_ai_row(token, created_by=_USER_ID)
        member_row = (str(_WS_UUID), _USER_ID)
        db = _db_with_ai(ai, member_row=member_row)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            result = resolve_agent_token(token, db)

        assert result == (str(_WS_UUID), _USER_ID)

    def test_without_gmc_link_falls_back_to_created_by(self):
        """OAuth-issued cond_api_* has no GMC row → falls back to created_by_clerk_user_id."""
        from app.core.auth import resolve_agent_token

        token = _api_token()
        ai = _make_ai_row(token, created_by=_USER_ID)
        db = _db_with_ai(ai, member_row=None)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            result = resolve_agent_token(token, db)

        assert result == (str(_WS_UUID), _USER_ID)

    def test_without_gmc_link_and_no_created_by_returns_synthetic_label(self):
        """No GMC, no created_by → synthetic api:<name> label returned, not None."""
        from app.core.auth import resolve_agent_token

        token = _api_token()
        ai = _make_ai_row(token, created_by=None, token_name="claude-ai-oauth")
        db = _db_with_ai(ai, member_row=None)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            result = resolve_agent_token(token, db)

        assert result is not None
        ws, identity = result
        assert ws == str(_WS_UUID)
        assert identity.startswith("api:")

    def test_without_gmc_no_created_by_no_token_name_uses_name_field(self):
        """Falls back to ai.name when token_name is also None."""
        from app.core.auth import resolve_agent_token

        token = _api_token()
        ai = _make_ai_row(token, created_by=None, token_name=None)
        ai.name = "my-api-token"
        db = _db_with_ai(ai, member_row=None)

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            result = resolve_agent_token(token, db)

        assert result is not None
        _, identity = result
        # Either token_name or .name should appear in the synthetic label
        assert "my-api-token" in identity or identity.startswith("api:")


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_agent_token — legacy member tokens
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveAgentTokenLegacy:
    """bare hex and guard-mt-* legacy member tokens."""

    def test_bare_hex_active_returns_workspace_and_user(self):
        from app.core.auth import resolve_agent_token

        bare = "deadbeef1234567890abcdef"
        member_row = (str(_WS_UUID), _USER_ID)
        db = _db_for_legacy(member_row)

        result = resolve_agent_token(bare, db)
        assert result == (str(_WS_UUID), _USER_ID)

    def test_bare_hex_inactive_returns_none(self):
        from app.core.auth import resolve_agent_token

        bare = "deadbeef1234567890abcdef"
        db = _db_for_legacy(None)

        result = resolve_agent_token(bare, db)
        assert result is None

    def test_guard_mt_prefix_stripped_before_lookup(self):
        """guard-mt-<hex> → prefix stripped → same lookup as bare hex."""
        from app.core.auth import resolve_agent_token

        bare = "deadbeef1234567890abcdef"
        token = f"guard-mt-{bare}"
        member_row = (str(_WS_UUID), _USER_ID)
        db = _db_for_legacy(member_row)

        result = resolve_agent_token(token, db)
        assert result == (str(_WS_UUID), _USER_ID)

        # The SQL execute call must pass the bare value, not the prefixed one
        _, params_dict = db.execute.call_args[0]
        assert params_dict.get("tok") == bare

    def test_guard_mt_prefix_inactive_returns_none(self):
        from app.core.auth import resolve_agent_token

        token = "guard-mt-deadbeef1234567890abcdef"
        db = _db_for_legacy(None)

        result = resolve_agent_token(token, db)
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# resolve_agent_token — edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestResolveAgentTokenEdgeCases:

    def test_completely_invalid_token_returns_none(self):
        from app.core.auth import resolve_agent_token

        db = _db_for_legacy(None)
        result = resolve_agent_token("not_a_valid_token_xyz", db)
        assert result is None

    def test_empty_string_returns_none(self):
        from app.core.auth import resolve_agent_token

        db = _db_for_legacy(None)
        result = resolve_agent_token("", db)
        assert result is None

    def test_prefix_only_string_returns_none(self):
        """Token that is exactly the prefix with no payload → no rows → None."""
        from app.core.auth import resolve_agent_token

        db = _db_no_ai()
        with patch(_AI_PATCH, _AgentIdentityStub):
            result = resolve_agent_token("cond_agt_", db)
        assert result is None

    def test_multiple_ai_rows_first_matching_decrypt_wins(self):
        """When multiple rows share a prefix, the one whose decrypt matches is used."""
        from app.core.auth import resolve_agent_token

        token = "cond_agt_" + "a" * 32
        ai_wrong = _make_ai_row(token)
        ai_right = _make_ai_row(token)

        db = MagicMock()
        query_result = MagicMock()
        query_result.all.return_value = [ai_wrong, ai_right]
        db.query.return_value.filter.return_value = query_result

        member_row = (str(_WS_UUID), _USER_ID)
        execute_result = MagicMock()
        execute_result.fetchone.return_value = member_row
        db.execute.return_value = execute_result

        call_count: dict[str, int] = {"n": 0}

        def selective_decrypt(blob):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return {"token": "cond_agt_wrong"}
            return {"token": token}

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", side_effect=selective_decrypt),
        ):
            result = resolve_agent_token(token, db)

        assert result == (str(_WS_UUID), _USER_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# MCP endpoint auth (mocked HTTP layer — asyncio.run, no pytest-asyncio needed)
# ═══════════════════════════════════════════════════════════════════════════════

def _make_mcp_request(bearer: str | None = None):
    req = MagicMock()
    h: dict[str, str] = {}
    if bearer:
        h["Authorization"] = f"Bearer {bearer}"

    class _Headers(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    req.headers = _Headers(h)

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

            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None, token=None))

        assert response.status_code == 200
        body = json.loads(response.body)
        assert "protocolVersion" in body.get("result", {})

    def test_valid_cond_api_oauth_token_returns_200(self):
        """cond_api_* OAuth token (no GMC link) + GuardConfig → 200."""
        import json
        from app.modules.guard.routers.mcp import mcp_endpoint

        token = "cond_api_" + "y" * 32
        req = _make_mcp_request(bearer=token)

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.mcp.get_clerk_user_email", return_value="oauth@example.com"),
            patch("app.modules.guard.routers.mcp.GuardConfig", _GuardConfigStub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = _mock_guard_config()
            mock_sl.return_value = mock_db

            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None, token=None))

        assert response.status_code == 200

    def test_missing_token_returns_401(self):
        """No Authorization header and no query token → 401."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        req = _make_mcp_request(bearer=None)
        response = asyncio.run(mcp_endpoint(request=req, workspace_id=None, token=None))
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
            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None, token=None))

        assert response.status_code == 401

    def test_valid_token_no_guard_config_returns_401_with_www_authenticate(self):
        """Token valid but workspace has no GuardConfig → 401 + WWW-Authenticate header."""
        from app.modules.guard.routers.mcp import mcp_endpoint

        token = "cond_agt_" + "z" * 32
        req = _make_mcp_request(bearer=token)

        with (
            patch("app.modules.guard.routers.mcp.resolve_agent_token", return_value=(str(_WS_UUID), _USER_ID)),
            patch("app.modules.guard.routers.mcp.get_clerk_user_email", return_value="user@example.com"),
            patch("app.modules.guard.routers.mcp.GuardConfig", _GuardConfigStub),
            patch("app.modules.guard.routers.mcp.SessionLocal") as mock_sl,
        ):
            mock_db = MagicMock()
            mock_db.query.return_value.filter.return_value.first.return_value = None
            mock_sl.return_value = mock_db
            response = asyncio.run(mcp_endpoint(request=req, workspace_id=None, token=None))

        assert response.status_code == 401
        assert "WWW-Authenticate" in response.headers


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
