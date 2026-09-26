"""Real SQL coverage for trial -> shared accounting, without query mocks."""
import json
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Column, MetaData, Table, UniqueConstraint, Uuid, text

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.modules.glens.trial_accounting import attach_trial_accounting
from app.modules.glens.trial_evidence import read_trial_evidence
from app.runtime.accounting.reader import AccountingReader
from app.runtime.accounting.request_evidence import AttemptEvidence
from tests.glens.test_trial_evidence import data, query, WS, OTHER  # noqa: F401

ALICE = UUID("10000000-0000-0000-0000-000000000001")
BOB = UUID("10000000-0000-0000-0000-000000000002")


@pytest.fixture
def accounting(data):
    db, add = data
    db.execute(text("ALTER TABLE guard_audit_events ADD COLUMN routing_meta JSON"))
    for old, new in [("alice-trial", ALICE), ("bob-trial", BOB)]:
        db.execute(text("UPDATE agent_identities SET id=:new WHERE id=:old"), {"new": str(new), "old": old})
    db.execute(text("INSERT INTO permissions VALUES (3, 'guard.spend.view_own'), (4, 'guard.spend.view_all')"))
    db.execute(text("INSERT INTO role_permissions VALUES (1, 3), (2, 3), (2, 4)"))
    model = LlmAttemptReceipt
    names = list(AttemptEvidence.__dataclass_fields__) + ["workspace_id", "agent_identity_id"]
    table = Table("llm_attempt_receipts", MetaData(), *[
        Column(name, Uuid(native_uuid=False) if isinstance(model.__table__.c[name].type, Uuid)
               else model.__table__.c[name].type, primary_key=name == "id") for name in names
    ], UniqueConstraint("request_id", "attempt_ordinal"))
    table.create(db.connection())
    def event(identity=ALICE, expected=1, **kwargs):
        row = add(identity=str(identity), **kwargs)
        if expected is not None:
            db.execute(text("UPDATE guard_audit_events SET routing_meta=:meta WHERE id=:id"), {
                "id": row["id"].hex, "meta": json.dumps({"attempts": [{}] * expected}),
            })
        return row
    def receipt(event, ordinal=0, **kwargs):
        row = dict(
            id=uuid4(), request_id=event["request_id"], attempt_ordinal=ordinal,
            workspace_id=event["workspace_id"], agent_identity_id=UUID(event["agent_identity_id"]),
            provider="anthropic", model="test-model", contract_version=1,
            pricing_version="snapshot-1", normalizer_version="normalizer-1", currency="USD",
            usage_origin="provider_reported", usage_completeness="complete",
            pricing_completeness="priced", execution_outcome="succeeded",
            total_input_tokens=100, total_output_tokens=20, cache_read_tokens=60,
            reasoning_output_tokens=5, calculated_cost_microdollars=1200,
        )
        row.update(kwargs)
        db.execute(table.insert().values(**row))
        return row
    return db, event, receipt


def result(db, user="alice", **kwargs):
    return attach_trial_accounting(db, user, read_trial_evidence(db, str(WS), user, query(**kwargs)))


def test_complete_receipt_and_breakdowns_are_not_added_twice(accounting):
    db, event, receipt = accounting
    row = event()
    paid = receipt(row)
    value = result(db)
    assert value.accounting_status == "ok"
    assert value.accounting_totals.input_tokens.value == 100
    assert value.accounting_totals.output_tokens.value == 20
    assert value.accounting_totals.calculated_cost_microdollars.value == 1200
    attempt = value.records[0].accounting.attempts[0]
    assert attempt.id == paid["id"]
    assert attempt.cache_read_tokens == 60 and attempt.reasoning_output_tokens == 5
    assert attempt.pricing_version == "snapshot-1"
    encoded = value.model_dump(mode="json")
    assert encoded["accounting_scope"] == "returned_records_only"
    assert encoded["records"][0]["accounting"]["attempts"][0]["id"] == str(paid["id"])


def test_fallback_counts_every_attempt_at_its_recorded_price(accounting):
    db, event, receipt = accounting
    row = event(expected=2)
    receipt(row, execution_outcome="failed", total_input_tokens=30, total_output_tokens=0, calculated_cost_microdollars=90)
    receipt(row, 1, provider="openai", model="fallback", pricing_version="snapshot-2", calculated_cost_microdollars=700)
    value = result(db)
    assert value.accounting_totals.input_tokens.value == 130
    assert value.accounting_totals.output_tokens.value == 20
    assert value.accounting_totals.calculated_cost_microdollars.value == 790
    assert [a.attempt_ordinal for a in value.records[0].accounting.attempts] == [0, 1]


def test_receipt_workspace_and_identity_must_match_authorized_event(accounting):
    db, event, receipt = accounting
    row = event()
    receipt(row, workspace_id=OTHER)
    receipt(row, 1, agent_identity_id=BOB)
    value = result(db)
    assert value.accounting_totals.receipt_count == 0
    assert value.accounting_totals.missing_request_count == 1
    assert value.accounting_totals.calculated_cost_microdollars.value is None


def test_missing_receipts_are_not_zero(accounting):
    db, event, _ = accounting
    event()
    value = result(db)
    assert value.accounting_status == "partial"
    assert value.accounting_totals.input_tokens.value is None
    assert value.accounting_totals.output_tokens.value is None
    assert value.accounting_totals.calculated_cost_microdollars.value is None
    assert value.records[0].accounting.missing_attempt_count == 1


def test_reported_zero_is_complete(accounting):
    db, event, receipt = accounting
    receipt(event(), total_input_tokens=0, total_output_tokens=0, calculated_cost_microdollars=0)
    value = result(db)
    assert value.accounting_status == "ok"
    assert value.accounting_totals.input_tokens.value == 0
    assert value.accounting_totals.calculated_cost_microdollars.value == 0


@pytest.mark.parametrize("changes,breakdown", [
    ({"usage_completeness": "partial"}, "partial"),
    ({"usage_completeness": "pending"}, "pending"),
    ({"usage_completeness": "unavailable", "total_input_tokens": None}, "unavailable"),
])
def test_incomplete_usage_is_preserved_and_not_settleable_cost(accounting, changes, breakdown):
    db, event, receipt = accounting
    receipt(event(), **changes)
    value = result(db)
    assert value.accounting_status == "partial"
    assert value.accounting_totals.usage_completeness == {breakdown: 1}
    assert value.accounting_totals.calculated_cost_microdollars.value is None


@pytest.mark.parametrize("changes", [
    {"pricing_completeness": "unpriced"}, {"pricing_completeness": "incomplete"},
    {"currency": "EUR"}, {"contract_version": 999}, {"calculated_cost_microdollars": None},
])
def test_unpriced_or_unsupported_cost_never_silently_enters_total(accounting, changes):
    db, event, receipt = accounting
    receipt(event(), **changes)
    value = result(db)
    assert value.accounting_status == "partial"
    assert value.accounting_totals.calculated_cost_microdollars.value is None


def test_partial_subtotals_and_ordinal_gaps_are_explicit(accounting):
    db, event, receipt = accounting
    row = event(expected=3)
    receipt(row)
    receipt(row, 2, calculated_cost_microdollars=300)
    value = result(db)
    assert value.records[0].accounting.missing_attempt_count == 1
    assert value.accounting_totals.calculated_cost_microdollars.value == 1500
    assert value.accounting_totals.calculated_cost_microdollars.status == "partial"


@pytest.mark.parametrize("kwargs", [{"expected": None}, {"lifecycle_state": "accepted"}])
def test_unknown_or_inflight_attempt_coverage_cannot_claim_complete(accounting, kwargs):
    db, event, receipt = accounting
    receipt(event(**kwargs))
    assert result(db).accounting_status == "partial"


def test_usage_without_request_link_is_unknown(accounting):
    db, event, receipt = accounting
    receipt(event())
    event(request_id=None, decision="blocked")
    value = result(db)
    assert value.accounting_unlinked_event_count == 1
    assert value.accounting_totals.calculated_cost_microdollars.value == 1200
    assert value.accounting_totals.calculated_cost_microdollars.status == "partial"


def test_spend_permission_is_separate_from_activity(accounting):
    db, event, receipt = accounting
    receipt(event())
    db.execute(text("DELETE FROM role_permissions WHERE role_id=1 AND permission_id=3"))
    value = result(db)
    assert value.status == "ok" and len(value.records) == 1
    assert value.accounting_status == "denied"
    assert value.accounting_totals is None and value.records[0].accounting is None


def test_workspace_spend_permission_required_even_for_activity_admin(accounting):
    db, event, receipt = accounting
    receipt(event())
    db.execute(text("DELETE FROM role_permissions WHERE role_id=2 AND permission_id=4"))
    assert result(db, "admin", scope="workspace").accounting_status == "denied"


def test_receipt_failure_preserves_activity_and_returns_no_fake_zero(accounting):
    db, event, _ = accounting
    event()
    db.execute(text("DROP TABLE llm_attempt_receipts"))
    value = result(db)
    assert value.status == "ok" and len(value.records) == 1
    assert value.accounting_status == "unavailable" and value.accounting_totals is None


def test_limit_only_accounts_for_returned_records(accounting):
    db, event, receipt = accounting
    for _ in range(3):
        receipt(event())
    value = result(db, limit=1)
    assert value.status == "partial" and value.total_matching == 3
    assert value.accounting_totals.request_count == 1
    assert value.accounting_totals.calculated_cost_microdollars.value == 1200


def test_duplicate_request_filters_do_not_double_count(accounting):
    db, event, receipt = accounting
    row = event()
    receipt(row)
    value = result(db, request_ids=[row["request_id"], row["request_id"]])
    assert value.accounting_totals.receipt_count == 1
    assert value.accounting_totals.calculated_cost_microdollars.value == 1200


def test_empty_request_batch_does_not_query_database():
    batch = AccountingReader(None).evidence_for_requests(workspace_id=WS, requests={})
    assert batch.requests == {} and batch.totals.input_tokens.value is None


def test_request_batch_is_bounded_before_database_query():
    with pytest.raises(ValueError, match="100"):
        AccountingReader(None).evidence_for_requests(workspace_id=WS, requests={uuid4(): ALICE for _ in range(101)})


def test_mixed_pricing_returns_only_supported_subtotal(accounting):
    db, event, receipt = accounting
    receipt(event())
    receipt(event(), pricing_completeness="unpriced", calculated_cost_microdollars=999999)
    value = result(db)
    assert value.accounting_totals.input_tokens.value == 200
    assert value.accounting_totals.input_tokens.status == "complete"
    assert value.accounting_totals.calculated_cost_microdollars.value == 1200
    assert value.accounting_totals.calculated_cost_microdollars.status == "partial"
    assert value.accounting_totals.pricing_completeness == {"priced": 1, "unpriced": 1}


def test_other_users_receipts_never_enter_own_totals(accounting):
    db, event, receipt = accounting
    receipt(event())
    receipt(event(identity=BOB), calculated_cost_microdollars=999999)
    assert result(db).accounting_totals.calculated_cost_microdollars.value == 1200


def test_reauthorization_does_not_leave_cached_spend_visible(accounting):
    db, event, receipt = accounting
    receipt(event())
    value = result(db)
    db.execute(text("DELETE FROM role_permissions WHERE role_id=1 AND permission_id=3"))
    attach_trial_accounting(db, "alice", value)
    assert value.accounting_status == "denied"
    assert value.accounting_totals is None and value.records[0].accounting is None


def test_registered_tool_attaches_accounting(accounting, monkeypatch):
    from types import SimpleNamespace
    from app.tools.registrations.lens.trial_evidence import get_trial_evidence
    db, event, receipt = accounting
    receipt(event())
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda *args: None)
    window = query()
    value = get_trial_evidence(SimpleNamespace(workspace_id=str(WS), clerk_user_id="alice"),
                               since=window.since, until=window.until)
    assert value["accounting_status"] == "ok"
    assert value["accounting_totals"]["calculated_cost_microdollars"] == {"value": 1200, "status": "complete"}
    json.dumps(value)
