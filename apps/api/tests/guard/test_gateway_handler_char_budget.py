"""#2399 characterization — budget reservation refusals in ``handle_gateway_request``.

Pins the fail-closed reservation contract (#2057 invariant 2) as wired
today: refused reservations finalize the accepted durable row as
``blocked`` with a specific rule id, return 402/503, never dispatch, and
never write receipts or settle.
"""
from __future__ import annotations

import json

import pytest

from tests.guard._gateway_handler_char_helpers import gw  # noqa: F401 — fixture

_REFUSALS = [
    ("EXCEEDED", 402, "exceeded", "guard.budget_cap_exceeded", "budget cap exceeded",
     {"ai_tool": "cursor", "hard_limit_usd": 0.01}),
    ("NOT_READY", 503, "not_ready", "guard.budget_ledger_not_ready",
     "budget ledger not ready (reconciler cold start)", None),
    ("REDIS_DOWN", 503, "redis_down", "guard.budget_ledger_unavailable", "budget ledger unavailable", None),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("decision,code,outcome,rule_id,reason,refusing", _REFUSALS)
async def test_reservation_refused_finalizes_blocked_and_never_dispatches(
    gw, decision, code, outcome, rule_id, reason, refusing,
):
    gw.ledger.decision = decision
    response, background = await gw.call()

    assert response.status_code == code
    assert json.loads(response.body) == {
        "type": "budget_reservation_refused", "outcome": outcome,
        "reason": reason, "refusing_budget": refusing,
    }
    # No server request id header on the refusal envelope.
    assert "x-conduct-request-id" not in response.headers

    assert gw.sent == []
    assert len(gw.ledger.reserve_calls) == 1
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    assert gw.receipts == []
    assert background.tasks == []
    # Durable row opened, then finalized as blocked (R6) — never left 'accepted'.
    assert len(gw.inserted) == 1
    assert len(gw.finalized) == 1
    row = gw.finalized[0]
    assert (row["decision"], row["execution_status"], row["rule_id"]) == ("blocked", "error", rule_id)
    assert row["result_summary"] == reason
    assert row["response_bytes"] is None
    assert gw.ledger.reserve_calls[0]["request_id"] == gw.inserted[0].kwargs["request_id"]
    # Only the ingress prompt gate ran.
    assert [c.gate for c in gw.policy_ctx] == ["prompt"]
    assert (gw.ticket.release_calls, gw.ticket.deferred) == (1, False)


@pytest.mark.asyncio
async def test_lookup_error_is_db_error_503(gw, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr("app.modules.guard.spend_lookup.lookup_applicable_budgets", _boom)

    response, _ = await gw.call()

    assert response.status_code == 503
    assert json.loads(response.body)["outcome"] == "db_error"
    assert json.loads(response.body)["reason"] == "budget lookup failed"
    assert gw.sent == []
    assert gw.finalized[0]["rule_id"] == "guard.budget_ledger_error"


@pytest.mark.asyncio
async def test_reserve_helper_raising_with_ledger_on_is_synthetic_db_error(gw, monkeypatch):
    """R7: an exception escaping the reserve wire is fail-CLOSED when the ledger is on."""
    def _boom(*a, **k):
        raise RuntimeError("estimator exploded")
    monkeypatch.setattr("app.modules.guard.gateway_lifecycle.estimate_budget_cents", _boom)

    response, _ = await gw.call()

    assert response.status_code == 503
    body = json.loads(response.body)
    assert (body["outcome"], body["reason"]) == ("db_error", "reserve raised: RuntimeError")
    assert gw.sent == [] and gw.receipts == []
    row = gw.finalized[0]
    assert (row["decision"], row["rule_id"], row["result_summary"]) == (
        "blocked", "guard.budget_ledger_error", "reserve raised: RuntimeError")


@pytest.mark.asyncio
async def test_reserve_helper_raising_with_ledger_off_dispatches(gw, monkeypatch):
    """Ledger kill switch off: a raising reserve wire falls through to dispatch (pre-PR-A behaviour)."""
    gw.ledger_enabled(False)

    def _boom(*a, **k):
        raise RuntimeError("estimator exploded")
    monkeypatch.setattr("app.modules.guard.gateway_lifecycle.estimate_budget_cents", _boom)

    response, _ = await gw.call()

    assert response.status_code == 200
    assert len(gw.sent) == 1
    assert gw.ledger.reserve_calls == [] and gw.ledger.commit_calls == []
    assert gw.finalized[0]["decision"] == "allowed"
    # Receipts still written; no reservation means reserved_microdollars is None.
    assert gw.receipts[0]["reserved_microdollars"] is None


@pytest.mark.asyncio
async def test_ledger_disabled_dispatches_without_reservation_or_settlement(gw):
    gw.ledger_enabled(False)

    response, _ = await gw.call()

    assert response.status_code == 200
    assert len(gw.sent) == 1
    assert gw.ledger.reserve_calls == []
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    assert len(gw.receipts) == 1
    assert gw.receipts[0]["reserved_microdollars"] is None


@pytest.mark.asyncio
async def test_no_hard_cap_budgets_dispatches_with_noop_settle(gw, monkeypatch):
    monkeypatch.setattr("app.modules.guard.spend_lookup.lookup_applicable_budgets", lambda *a, **k: [])
    gw.ledger.reservations = []

    response, _ = await gw.call()

    assert response.status_code == 200
    assert len(gw.sent) == 1
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    assert gw.receipts[0]["reserved_microdollars"] is None


@pytest.mark.asyncio
async def test_receipts_not_durable_leaves_reservation_open(gw, monkeypatch):
    """P1-D: receipt write failure skips settlement (reservation left for recovery)."""
    def _fail(**kwargs):
        raise RuntimeError("receipts table down")
    monkeypatch.setattr("app.runtime.accounting.shadow_writer.write_receipts_for_attempts", _fail)

    response, _ = await gw.call()

    assert response.status_code == 200
    assert gw.finalized[0]["decision"] == "allowed"
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
