"""#2399 characterization — auth and prompt-gate refusals in ``handle_gateway_request``.

Pins: missing / unrecognized / expired token responses, auth-cache staleness
as implemented today, and the prompt-gate BLOCK / APPROVAL / spend_cap
short-circuits (status + body, audit row, no upstream call, no durable row,
no reservation, admission released).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.core.auth_cache import AuthCache, CachedAuth
from tests.guard._gateway_handler_char_helpers import (  # noqa: F401 — gw is a fixture
    COND_MODEL, IDENTITY, MEMBER, PATH, TOKEN, WS, audit_tasks, gw, policy,
)


def _error(response) -> dict:
    return json.loads(response.body)["error"]


def _nothing_downstream(gw) -> None:
    assert gw.sent == []
    assert gw.inserted == [] and gw.finalized == []
    assert gw.ledger.reserve_calls == [] and gw.receipts == []


# ── auth ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@pytest.mark.parametrize("header", [None, "Bearer not-a-conduct-token", "cond_agt_missing_bearer_prefix"])
async def test_missing_or_malformed_token_is_401_before_any_lookup(gw, header):
    response, background = await gw.call(headers={"authorization": header})

    assert response.status_code == 401
    assert _error(response) == {
        "type": "conduct_guard_proxy",
        "message": "Missing or malformed Conduct member token — run `conduct login`",
    }
    gw.auth.assert_not_called()
    _nothing_downstream(gw)
    assert audit_tasks(background) == []
    assert gw.policy_ctx == []
    # Admission is acquired AFTER auth, so there is no ticket to release.
    assert gw.ticket.release_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("expired,message", [
    (False, "Conduct member token not recognized — run `conduct login`"),
    (True, "Conduct session expired — run `conduct login`"),
])
async def test_unrecognized_or_expired_token_is_401_from_db_auth(gw, monkeypatch, expired, message):
    monkeypatch.setattr(
        "app.modules.guard.gateway_helpers._resolve_gateway_auth", gw.real_auth)
    monkeypatch.setattr("app.core.auth.resolve_agent_token", lambda token, db: None)
    monkeypatch.setattr("app.core.auth.token_is_expired", lambda token, db: expired)

    response, background = await gw.call()

    assert response.status_code == 401
    assert _error(response) == {"type": "conduct_guard_proxy", "message": message}
    _nothing_downstream(gw)
    assert audit_tasks(background) == []  # auth refusals write no audit row
    assert gw.ticket.release_calls == 0


@pytest.mark.asyncio
async def test_auth_cache_hit_skips_db_and_serves_stale_until_invalidated(gw, monkeypatch):
    """Auth staleness (#2057 invariant 1) as implemented today.

    A cache hit bypasses the DB resolver entirely, so a token revoked in the
    DB keeps working until the entry expires or is invalidated. After
    invalidation a ``None`` cache result does NOT refuse by itself — the
    handler falls through to the DB resolver, which owns the 401.
    """
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    fetch = AsyncMock(return_value=CachedAuth(
        workspace_id=WS, clerk_user_id=MEMBER, agent_identity_id=IDENTITY,
        agent_risk_tier=None, is_internal=False, token_expires_at=None))
    cache = AuthCache(fetch=fetch, cache_ttl_seconds=60)
    monkeypatch.setattr("app.core.auth_cache.get_auth_cache", lambda: cache)

    first, _ = await gw.call()
    assert first.status_code == 200
    assert fetch.await_count == 1
    gw.auth.assert_not_called()
    assert gw.inserted[0].kwargs["agent_identity_id"] == IDENTITY

    fetch.return_value = None  # token revoked at the source of truth
    stale, _ = await gw.call()
    assert stale.status_code == 200  # served from cache
    assert fetch.await_count == 1
    gw.auth.assert_not_called()

    from app.guard.router import fail_closed
    gw.auth.return_value = fail_closed(401, "Conduct member token not recognized — run `conduct login`")
    cache.invalidate_token(TOKEN)
    refused, _ = await gw.call()
    assert refused.status_code == 401
    assert fetch.await_count == 2
    gw.auth.assert_called_once()
    assert len(gw.sent) == 2


@pytest.mark.asyncio
async def test_internal_agent_key_bypasses_auth_cache(gw, monkeypatch):
    cache = AuthCache(fetch=AsyncMock(), cache_ttl_seconds=60)
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    monkeypatch.setattr("app.core.auth_cache.get_auth_cache", lambda: cache)

    response, _ = await gw.call(headers={"authorization": None, "x-conductai-internal": "cond_agt_internal"})

    assert response.status_code == 200
    cache._fetch.assert_not_awaited()
    kwargs = gw.auth.call_args.kwargs
    assert kwargs["token"] is None and kwargs["internal_key"] == "cond_agt_internal"
    assert kwargs["needs_agent_validation"] is True and kwargs["needs_run_token_validation"] is False


# ── prompt gate ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_prompt_gate_block_is_403_with_receipt_and_blocked_audit(gw):
    gw.set_policy(policy("BLOCK", rule_id="rule-pii", reason="PII in prompt"))
    response, background = await gw.call()

    assert response.status_code == 403
    err = _error(response)
    assert err["type"] == "guard_block"
    assert err["rule"] == "rule-pii"
    assert err["message"].startswith("PII in prompt\n→ Receipt: ")
    assert err["receipt_url"].endswith(err["receipt_id"])
    assert "x-conduct-request-id" not in response.headers

    _nothing_downstream(gw)
    assert [c.gate for c in gw.policy_ctx] == ["prompt"]
    tasks = audit_tasks(background)
    assert len(tasks) == 1
    assert tasks[0].name == "record"
    assert tasks[0].args[:7] == (WS, MEMBER, "unknown", "openai", COND_MODEL, "blocked", "rule-pii")
    kwargs = tasks[0].kwargs
    assert kwargs["receipt_id"] == err["receipt_id"]
    assert kwargs["agent_identity_id"] == IDENTITY and kwargs["route"] == PATH
    assert kwargs["routing_meta"]["gateway_version"] == "v2"
    assert kwargs["response_bytes"] is None
    # No reservation was ever taken, so there is nothing to release.
    assert gw.ledger.release_calls == [] and gw.ledger.commit_calls == []
    assert (gw.ticket.release_calls, gw.ticket.deferred) == (1, False)


@pytest.mark.asyncio
async def test_prompt_gate_spend_cap_source_is_429_budget_exceeded(gw):
    gw.set_policy(policy("BLOCK", source="spend_cap", reason="Monthly AI budget reached."))
    response, background = await gw.call()

    assert response.status_code == 429
    err = _error(response)
    assert err["type"] == "guard_budget_exceeded"
    assert err["message"].startswith("Monthly AI budget reached.\n→ Receipt: ")
    _nothing_downstream(gw)
    tasks = audit_tasks(background)
    assert len(tasks) == 1
    assert tasks[0].args[5:7] == ("budget_exceeded", None)
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_prompt_gate_approval_short_circuits_without_upstream(gw):
    gw.set_policy(policy("APPROVAL", rule_id="rule-approve", reason="needs a human"))
    response, background = await gw.call()

    assert response.status_code == 428
    _nothing_downstream(gw)
    tasks = audit_tasks(background)
    assert len(tasks) == 1
    assert tasks[0].args[:5] == (WS, MEMBER, "unknown", "openai", COND_MODEL)
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_prompt_gate_warn_dispatches_and_records_warned(gw):
    gw.set_policy(policy("WARN", rule_id="rule-warn", reason="careful"))
    response, _ = await gw.call()

    assert response.status_code == 200
    assert len(gw.sent) == 1
    row = gw.finalized[0]
    assert (row["decision"], row["rule_id"], row["execution_status"]) == ("warned", "rule-warn", "ok")
