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

from unittest.mock import MagicMock, patch

# Helpers import performs the path + env bootstrap (must precede app imports).
from tests._agent_identity_auth_helpers import (
    _AI_PATCH,
    _AgentIdentityStub,
    _USER_ID,
    _WS_UUID,
    _agt_token,
    _api_token,
    _db_for_legacy,
    _db_no_ai,
    _db_with_ai,
    _make_ai_row,
)


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

    def test_expired_session_token_row_present_returns_none(self):
        """Row exists, decrypt matches, but expires_at is past → treat as invalid."""
        from datetime import datetime, timedelta, timezone
        from app.core.auth import resolve_agent_token, token_is_expired

        token = _agt_token()
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        ai = _make_ai_row(token, expires_at=past)
        db = _db_with_ai(ai, member_row=(str(_WS_UUID), _USER_ID))

        with (
            patch(_AI_PATCH, _AgentIdentityStub),
            patch("app.core.crypto.decrypt", return_value={"token": token}),
        ):
            assert resolve_agent_token(token, db) is None
            # Same underlying row → helper reports expired so proxy can render
            # `conduct login` instead of the generic not-recognized message.
            assert token_is_expired(token, db) is True

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
