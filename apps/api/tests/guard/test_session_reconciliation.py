"""Session links and accounting boundaries against disposable Postgres."""
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.models.workspace import Workspace
from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.modules.guard.models import GuardAuditEvent
from app.modules.guard.session_reconciliation import session_evidence
from app.modules.guard.routers.events import session_reconciliation
from app.runtime.accounting.contracts import CONTRACT_VERSION


@pytest.fixture
def database():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "test" not in (make_url(url).database or ""):
        pytest.skip("Requires a dedicated test database")
    engine = create_engine(url)
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    ws = Workspace(name="Session evidence test", owner_id="owner")
    db.add(ws)
    db.flush()
    try:
        yield db, ws.id
    finally:
        db.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


def report(db, ws, session=None, actor="owner", estimate=500, tool="codex-cli"):
    row = GuardAuditEvent(workspace_id=ws, clerk_user_id=actor, ai_tool=tool,
                          hook_session_id=str(session or uuid4()), tool_call="session_usage",
                          decision="audited", tokens_before=100, tokens_after=20,
                          routing_meta={"session_usage": {"source": "client_reported", "estimated_microdollars": estimate}})
    db.add(row)
    db.flush()
    return row


def receipt(db, event, *, request=None, ordinal=0, cost=400, actor=None, session=None, ws=None, count=1, response_id=None):
    from uuid import UUID
    request = request or uuid4()
    row = LlmAttemptReceipt(workspace_id=ws or event.workspace_id, request_id=request,
        attempt_ordinal=ordinal, contract_version=CONTRACT_VERSION, developer_external_id=actor or event.clerk_user_id,
        hook_session_id=session or UUID(event.hook_session_id), source="gateway", provider="test", model="test",
        operation="chat", execution_outcome="succeeded", total_input_tokens=100, total_output_tokens=20,
        usage_origin="provider", usage_completeness="complete", calculated_cost_microdollars=cost,
        pricing_completeness="priced" if cost is not None else "unpriced", currency="USD",
        calculation_provenance={"provider_response_id": response_id} if response_id else {})
    db.add(row)
    if ordinal == 0:
        db.add(GuardAuditEvent(workspace_id=ws or event.workspace_id, clerk_user_id=actor or event.clerk_user_id,
            ai_tool="codex-cli", source="gateway", decision="allowed", request_id=request,
            lifecycle_state="finalized", routing_meta={"attempts": [{"attempt_ordinal": n} for n in range(count)]}))
    db.flush()
    return request


def test_exact_session_link_keeps_sources_separate_and_retries(database):
    db, ws = database
    event = report(db, ws)
    report(db, ws, event.hook_session_id, estimate=600, tool="codex-desktop")
    request = receipt(db, event, count=2)
    receipt(db, event, request=request, ordinal=1, cost=300)
    result = session_evidence(db, event)
    assert result["reported"]["estimated_microdollars"] == 1100
    assert result["reported"]["input_tokens"] == 200
    assert result["gateway"]["calculated_cost_microdollars"] == {"value": 700, "status": "complete"}
    assert result["gateway"]["receipt_count"] == 2
    assert result["gateway"]["request_count"] == 1
    assert result["combined_cost_microdollars"] is None
    assert result["overlap"] == "unknown"
    assert result["reported"]["budget_eligible"] is False
    assert session_evidence(db, event) == result
    assert not db.dirty and not db.new


def test_no_time_or_model_matching_and_no_other_actor_data(database):
    db, ws = database
    event = report(db, ws)
    report(db, ws, event.hook_session_id, actor="other", estimate=999)
    receipt(db, event, actor="other")
    receipt(db, event, session=uuid4())
    other_ws = Workspace(name="Other", owner_id="owner")
    db.add(other_ws); db.flush()
    receipt(db, event, ws=other_ws.id)
    result = session_evidence(db, event)
    assert result["reported"]["snapshot_count"] == 1
    assert result["gateway"]["receipt_count"] == 0
    assert result["link_status"] == "unlinked"
    assert result["gateway"]["calculated_cost_microdollars"]["value"] is None


def test_late_receipts_and_unpriced_are_preserved(database):
    db, ws = database
    event = report(db, ws, estimate=None)
    assert session_evidence(db, event)["link_status"] == "unlinked"
    receipt(db, event, cost=None)
    result = session_evidence(db, event)
    assert result["link_status"] == "session_id_linked"
    assert result["reported"]["cost_status"] == "unpriced"
    assert result["gateway"]["calculated_cost_microdollars"] == {"value": None, "status": "unavailable"}


def test_missing_attempt_is_partial(database):
    db, ws = database
    event = report(db, ws)
    receipt(db, event, count=2)
    result = session_evidence(db, event)
    assert result["gateway"]["calculated_cost_microdollars"] == {"value": 400, "status": "partial"}


def test_endpoint_checks_spend_ownership(database, monkeypatch):
    db, ws = database
    event = report(db, ws)
    db.execute(text("INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) VALUES (:ws, 'reader', 'developer', now())"), {"ws": ws})
    def permission(**kwargs):
        assert kwargs["permission"].startswith("guard.spend.")
        if kwargs["permission"].endswith("view_all"):
            raise HTTPException(403)
    monkeypatch.setattr("app.modules.guard.event_access.check_permission", permission)
    with pytest.raises(HTTPException) as error:
        session_reconciliation(event.id, str(ws), "reader", "developer", db)
    assert error.value.status_code == 404
    own = report(db, ws, actor="reader")
    assert session_reconciliation(own.id, str(ws), "reader", "developer", db)["reported"]["snapshot_count"] == 1


def test_nonmember_cannot_read_even_with_permission_override(database):
    db, ws = database
    event = report(db, ws)
    with pytest.raises(HTTPException) as error:
        session_reconciliation(event.id, str(ws), "stranger", "admin", db)
    assert error.value.status_code == 403


def test_partial_report_prices_are_subtotals_not_zero(database):
    db, ws = database
    event = report(db, ws)
    report(db, ws, event.hook_session_id, estimate=None)
    result = session_evidence(db, event)
    assert result["reported"]["cost_status"] == "partial"
    assert result["reported"]["estimated_microdollars"] == 500
    assert result["reported"]["unpriced_snapshot_count"] == 1


def test_receipt_limit_is_explicitly_partial(database):
    db, ws = database
    event = report(db, ws)
    for _ in range(101):
        receipt(db, event)
    result = session_evidence(db, event)
    assert result["gateway"]["truncated"] is True
    assert result["gateway"]["request_count"] == 100
    assert result["gateway"]["calculated_cost_microdollars"]["status"] == "partial"


def test_report_limit_is_explicitly_partial(database):
    db, ws = database
    event = report(db, ws)
    for _ in range(1000):
        report(db, ws, event.hook_session_id)
    result = session_evidence(db, event)
    assert result["reported"]["snapshot_count"] == 1000
    assert result["reported"]["truncated"] is True
    assert result["reported"]["cost_status"] == "partial"


def test_anonymous_session_is_not_a_correlation_key(database):
    db, ws = database
    event = report(db, ws, actor=None)
    with pytest.raises(ValueError, match="authenticated actor"):
        session_evidence(db, event)


def linked_report(db, ws, response_id="msg_fixture", **overrides):
    event = report(db, ws)
    event.routing_meta = {"session_usage": {"source": "client_reported", "estimated_microdollars": 500,
        "cost_status": "estimated", "pricing_version": "fixture-v1", "slices": [{
            "provider": "test", "model": "test", "provider_response_id": response_id,
            "uncached_input_tokens": 100, "cache_read_tokens": 0, "cache_write_tokens": 0,
            "output_tokens": 20, "estimated_microdollars": 500, **overrides}]}}
    db.flush()
    return event


def test_protocol_response_links_without_session_header_and_never_adds_estimate(database):
    db, ws = database
    event = linked_report(db, ws)
    request = receipt(db, event, response_id="msg_fixture", session=uuid4())
    result = session_evidence(db, event)
    assert result["link_status"] == "request_id_linked"
    assert result["matching"]["complete"]
    assert result["combined_cost_microdollars"] == 400
    assert result["request_ids"] == [str(request)]
    assert result["rollups"]["reported"][0]["estimated_microdollars"] == 500
    assert result["rollups"]["gateway"][0]["totals"]["calculated_cost_microdollars"]["value"] == 400


def test_explicit_gateway_request_id_is_scoped_and_checked(database):
    db, ws = database
    event = linked_report(db, ws, response_id=None)
    request = receipt(db, event, session=uuid4())
    part = event.routing_meta["session_usage"]["slices"][0]
    event.routing_meta = {"session_usage": {**event.routing_meta["session_usage"],
        "slices": [{**part, "gateway_request_id": str(request)}]}}
    db.flush()
    assert session_evidence(db, event)["combined_cost_microdollars"] == 400
    other = linked_report(db, ws)
    foreign = receipt(db, other, actor="another-user", session=uuid4())
    event.routing_meta = {"session_usage": {**event.routing_meta["session_usage"],
        "slices": [{**part, "gateway_request_id": str(foreign)}]}}
    db.flush()
    result = session_evidence(db, event)
    assert result["matching"]["unmatched_slice_count"] == 1
    assert result["combined_cost_microdollars"] is None
    assert str(foreign) not in result["request_ids"]


def test_duplicate_response_ids_are_ambiguous_not_inferred_by_model(database):
    db, ws = database
    event = linked_report(db, ws)
    receipt(db, event, response_id="msg_fixture")
    receipt(db, event, response_id="msg_fixture")
    result = session_evidence(db, event)
    assert result["matching"]["unmatched_slice_count"] == 1
    assert result["combined_cost_microdollars"] is None


@pytest.mark.parametrize("overrides", [{"model": "different"}, {"provider": "different"}, {"output_tokens": 19}])
def test_conflicting_model_or_token_totals_cannot_claim_combined_cost(database, overrides):
    db, ws = database
    event = linked_report(db, ws, **overrides)
    receipt(db, event, response_id="msg_fixture")
    result = session_evidence(db, event)
    assert not result["matching"]["complete"]
    assert result["combined_cost_microdollars"] is None


def test_partial_stream_deltas_link_once_and_gateway_retries_remain_recorded(database):
    db, ws = database
    event = linked_report(db, ws, output_tokens=10)
    second = linked_report(db, ws, uncached_input_tokens=0, output_tokens=10)
    second.hook_session_id = event.hook_session_id
    request = receipt(db, event, response_id="msg_fixture", count=2)
    receipt(db, event, request=request, ordinal=1, cost=300)
    db.flush()
    result = session_evidence(db, event)
    assert result["matching"]["complete"]
    assert len(result["matching"]["linked_attempts"]) == 1
    assert result["combined_cost_microdollars"] == 700
    assert result["gateway"]["calculated_cost_microdollars"]["value"] == sum(
        row["totals"]["calculated_cost_microdollars"]["value"] for row in result["rollups"]["gateway"])
