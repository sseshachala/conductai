"""Session-usage cost on audit rows, Gateway-wins dedupe and budget isolation (Postgres)."""
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSession, GuardSpendBudget
from app.modules.guard.routers import events_ingest
from app.modules.guard.routers.events import SessionUsageReport
from app.modules.guard.routers.spend_budget_check import budget_check
from app.modules.guard.routers.spend_budgets import _current_month_cost
from app.modules.guard.session_coverage import apply_session_cost
from app.runtime.accounting.pricing import PricingService
from app.runtime.accounting.reader import AccountingReader
from tests.guard.test_session_reconciliation import database, receipt, report  # noqa: F401  (fixtures)
from tests.guard.test_session_usage_pricing import LITELLM, OUR_TABLE

NOW = datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def pricing(monkeypatch):
    service = PricingService(OUR_TABLE)
    monkeypatch.setattr("app.modules.guard.session_usage.default_pricing_service", lambda: service)
    monkeypatch.setattr("app.runtime.litellm_rates._cost_map", lambda: LITELLM)


def part(**kw):
    return {"model": "claude-opus-5-5", "provider": None, "uncached_input_tokens": 1000,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "output_tokens": 100, **kw}


def usage_report(ws, session, parts, tool="claude-code"):
    return SessionUsageReport(workspace_id=ws, hook_session_id=session, snapshot_id=uuid4(), observed_at=NOW,
                              ai_tool=tool, input_tokens=sum(p["uncached_input_tokens"] + p["cache_read_tokens"]
                              + p["cache_write_tokens"] for p in parts),
                              output_tokens=sum(p["output_tokens"] for p in parts), usage=parts)


class Event:
    cost_usd_before = cost_usd_after = _session_usage = None


def gateway_receipt(db, ws, session, response_id=None, actor="owner"):
    event = report(db, ws, session, actor=actor)
    request = receipt(db, event, response_id=response_id, session=UUID(str(session)), actor=actor)
    db.execute(update(LlmAttemptReceipt).where(LlmAttemptReceipt.request_id == request)
               .values(provider="anthropic", model="claude-opus-5-5"))
    return request


def priced(db, ws, parts, session=None, actor="owner"):
    session = session or uuid4()
    event = Event()
    apply_session_cost(event, usage_report(ws, session, parts), db, ws, actor, None)
    return event


def test_priced_report_sets_both_cost_columns(database):
    db, ws = database
    event = priced(db, ws, [part()])
    assert event.cost_usd_before == event.cost_usd_after == pytest.approx(0.006)
    assert event._session_usage["budget_eligible"] is False


def test_unpriced_report_leaves_cost_null(database):
    db, ws = database
    event = priced(db, ws, [part(model="mystery-model")])
    assert event.cost_usd_before is None and event.cost_usd_after is None
    assert event._session_usage["cost_status"] == "unpriced"


def test_response_id_match_is_covered_by_gateway_and_excluded(database):
    db, ws = database
    gateway_receipt(db, ws, uuid4(), response_id="msg_covered")
    event = priced(db, ws, [part(provider_response_id="msg_covered"), part(provider_response_id="msg_other")])
    first, second = event._session_usage["slices"]
    assert (first["covered_by"], first["estimated_microdollars"]) == ("gateway", 0)
    assert "covered_by" not in second
    assert event.cost_usd_after == pytest.approx(0.006)  # only the uncovered slice


def test_fully_covered_report_costs_zero_not_null(database):
    db, ws = database
    gateway_receipt(db, ws, uuid4(), response_id="msg_covered")
    event = priced(db, ws, [part(provider_response_id="msg_covered")])
    assert event.cost_usd_after == 0 and event._session_usage["cost_status"] == "estimated"


def test_idless_slices_in_session_with_receipts_are_gateway_session(database):
    db, ws = database
    session = uuid4()
    gateway_receipt(db, ws, session)
    event = priced(db, ws, [part(model="gpt-6.1-sol", provider="openai"), part(model="gpt-6.1-sol", provider="openai")],
                   session=session)
    assert [s["covered_by"] for s in event._session_usage["slices"]] == ["gateway_session"] * 2
    assert event.cost_usd_after == 0


def test_receipts_of_other_actor_or_session_do_not_cover(database):
    db, ws = database
    session = uuid4()
    gateway_receipt(db, ws, session, actor="someone-else")
    gateway_receipt(db, ws, uuid4())
    event = priced(db, ws, [part(model="gpt-6.1-sol", provider="openai")], session=session)
    assert "covered_by" not in event._session_usage["slices"][0]
    assert event.cost_usd_after == pytest.approx(0.002 + 0.001)


def test_ingest_endpoint_writes_cost_to_hook_event(database, monkeypatch):
    db, ws = database
    db.add(GuardConfig(workspace_id=ws, invite_code=uuid4().hex))
    db.flush()
    captured = {}
    monkeypatch.setattr(events_ingest, "ingest_event", lambda event, *a, **k: captured.setdefault("event", event))
    request = type("R", (), {"state": type("S", (), {"guard_hook_identity": None})()})()
    body = usage_report(ws, uuid4(), [part()])
    events_ingest.ingest_session_usage(body, request, None, db, (str(ws), "owner"))
    assert captured["event"].cost_usd_after == pytest.approx(0.006)
    assert captured["event"].cost_usd_before == captured["event"].cost_usd_after


def seed_budget(db, ws, tool_call, cost):
    db.add(GuardConfig(workspace_id=ws, invite_code=uuid4().hex))
    db.add(GuardSpendBudget(workspace_id=ws, monthly_limit_usd=100.0, hard_limit_usd=1.0, hard_cap_enabled=True))
    db.add(GuardAuditEvent(workspace_id=ws, clerk_user_id="owner", ai_tool="claude-code", tool_call=tool_call,
                           decision="audited", cost_usd_after=cost, ts=NOW))
    db.flush()


def test_budget_enforcement_ignores_client_reported_cost(database):
    db, ws = database
    seed_budget(db, ws, "session_usage", 5.0)
    result = budget_check(workspace_id=str(ws), clerk_user_id=None, ai_tool=None, transport=None, db=db)
    assert result.hard_blocked is False and result.monthly_cost_usd == 0.0
    assert _current_month_cost(db, ws, None) == 0.0
    since = NOW - timedelta(days=1)
    assert AccountingReader(db).spend_micros_by_workspace(workspace_id=ws, since=since) == {None: 0}


def test_budget_enforcement_still_counts_other_audit_cost(database):
    db, ws = database
    seed_budget(db, ws, "Bash", 5.0)
    assert budget_check(workspace_id=str(ws), clerk_user_id=None, ai_tool=None, transport=None, db=db).hard_blocked is True
    assert _current_month_cost(db, ws, None) == 5.0


def test_ingest_prices_new_models_from_registry(database, monkeypatch):
    db, ws = database
    service = PricingService()
    monkeypatch.setattr("app.modules.guard.session_usage.default_pricing_service", lambda: service)
    monkeypatch.setattr("app.runtime.litellm_rates._cost_map", lambda: {})
    event = priced(db, ws, [part(), part(model="gpt-6.1-sol", provider="openai")])
    assert event.cost_usd_after == pytest.approx(0.006 + 0.003)
    assert all("pricing_source" not in s for s in event._session_usage["slices"])


def test_redis_rebuild_excludes_client_reported_cost(database):
    import fakeredis
    from app.core.budget_ledger import BudgetLedger
    from app.core.budget_ledger_keys import _scope_keys, monthly_period_key

    db, ws = database
    seed_budget(db, ws, "session_usage", 5.0)
    db.add(GuardAuditEvent(workspace_id=ws, clerk_user_id="owner", ai_tool="claude-code", tool_call="Bash",
                           decision="audited", cost_usd_after=2.0, ts=NOW))
    db.flush()
    redis = fakeredis.FakeRedis(decode_responses=True)
    BudgetLedger(redis_client=redis).reconcile(db, str(ws), None)
    keys = _scope_keys(str(ws), None, None, None, monthly_period_key())
    assert int(redis.get(keys["committed"])) == 2_000_000
