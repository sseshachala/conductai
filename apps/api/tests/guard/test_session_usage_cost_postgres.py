"""Session-usage cost on audit rows, Gateway-wins dedupe, budget isolation and the one-shot backfill (Postgres)."""
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
from scripts import backfill_session_usage_cost_2026_10 as backfill
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


def seed_backfill(db, ws):
    """priced, gateway-covered and unpriced rows after the cutover, plus rows the backfill must not touch."""
    gateway_receipt(db, ws, uuid4(), response_id="msg_covered")
    gsession = GuardSession(workspace_id=ws, ai_tool="claude-code", started_at=NOW)
    db.add(gsession)
    db.flush()
    rows = {}
    for name, parts, ts in [
        ("priced", [part()], datetime(2026, 10, 2, 12, tzinfo=timezone.utc)),
        ("covered", [part(provider_response_id="msg_covered")], datetime(2026, 10, 2, 13, tzinfo=timezone.utc)),
        ("unpriced", [part(model="mystery-model")], datetime(2026, 10, 3, 9, tzinfo=timezone.utc)),
        ("before_cutoff", [part()], datetime(2026, 9, 1, tzinfo=timezone.utc)),
    ]:
        evidence = {"source": "client_reported", "observed_at": ts.isoformat(), "slices": parts}
        row = report(db, ws, uuid4(), estimate=None)
        row.routing_meta, row.ts, row.ai_tool = {"session_usage": evidence}, ts, "claude-code"
        row.session_id = gsession.id if name == "priced" else None
        rows[name] = row
    already = report(db, ws, uuid4(), estimate=None)
    already.ts, already.cost_usd_after = datetime(2026, 10, 4, tzinfo=timezone.utc), 7.0
    rows["already_costed"] = already
    db.flush()
    return rows, gsession


def snapshot(rows):
    return {k: (r.cost_usd_before, r.cost_usd_after, r.routing_meta) for k, r in rows.items()}


def test_backfill_dry_run_writes_nothing(database):
    db, ws = database
    rows, gsession = seed_backfill(db, ws)
    before = snapshot(rows)
    stats = backfill.run(db, apply=False)
    backfill.report(stats, False)
    db.expire_all()
    assert snapshot(rows) == before
    assert stats["rows"] == 4 and stats["legacy_no_slices"] == 1  # the receipt helper adds a totals-only report
    assert stats["priced_rows"] == 2 and stats["unpriced_rows"] == 1
    assert stats["covered_slices"] == {"gateway": 1}
    assert stats["unpriced_slices"] == {"missing_model_or_provider": 1}
    assert stats["by_day_tool"][("2026-10-02", "claude-code")] == [2, pytest.approx(0.006)]
    assert (gsession.total_cost_usd or 0) == 0


def test_backfill_apply_prices_and_is_idempotent(database):
    db, ws = database
    rows, gsession = seed_backfill(db, ws)
    backfill.run(db, apply=True)
    db.expire_all()
    assert rows["priced"].cost_usd_before == rows["priced"].cost_usd_after == pytest.approx(0.006)
    assert rows["priced"].routing_meta["session_usage"]["slices"][0]["provider_inferred"] == "anthropic"
    assert rows["covered"].cost_usd_after == 0
    assert rows["covered"].routing_meta["session_usage"]["slices"][0]["covered_by"] == "gateway"
    assert rows["unpriced"].cost_usd_after is None
    assert rows["before_cutoff"].cost_usd_after is None and rows["already_costed"].cost_usd_after == 7.0
    assert gsession.total_cost_usd == pytest.approx(0.006)
    first = snapshot(rows)
    backfill.run(db, apply=True)
    db.expire_all()
    assert snapshot(rows) == first
    assert gsession.total_cost_usd == pytest.approx(0.006)
    assert db.execute(select(GuardAuditEvent.id).where(GuardAuditEvent.cost_usd_after.is_(None),
                      GuardAuditEvent.ts >= backfill.SINCE)).all()  # only the still-unpriced row
