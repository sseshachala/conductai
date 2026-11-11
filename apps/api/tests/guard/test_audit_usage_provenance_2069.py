"""#2069 — Flight Recorder token usage: provenance, null vs zero, attempts."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4


from app.guard import audit
from app.guard.audit import _audit_usage
from app.modules.guard.event_usage import _row_state
from app.modules.guard.routers.events_common import client_usage_provenance
from app.runtime.accounting.request_evidence import AttemptEvidence, _totals


def _usage(response_bytes, *, provider="anthropic", decision="allowed", routing_meta=None,
           execution_status="ok", body=None):
    return _audit_usage(
        provider=provider, model="claude-sonnet-4-6",
        body={"model": "m", "messages": [{"role": "user", "content": "hello world"}]} if body is None else body,
        response_bytes=response_bytes, routing_meta=routing_meta,
        execution_status=execution_status, decision=decision,
    )


def test_anthropic_json_zero_counts_are_known_zero_not_missing():
    u = _usage(b'{"usage":{"input_tokens":0,"output_tokens":0}}')
    assert (u.input_tokens, u.output_tokens) == (0, 0)
    assert (u.source, u.status) == ("provider_reported", "complete")


def test_openai_chat_json_zero_completion_tokens():
    u = _usage(b'{"usage":{"prompt_tokens":5,"completion_tokens":0}}', provider="openai")
    assert (u.input_tokens, u.output_tokens) == (5, 0)
    assert u.status == "complete"


def test_openai_responses_json_zero_input():
    u = _audit_usage(
        provider="openai", model="gpt-x", body={"input": "x"},
        response_bytes=b'{"usage":{"input_tokens":0,"output_tokens":3}}',
        routing_meta={"operation": "/v1/responses"}, execution_status="ok", decision="allowed",
    )
    assert (u.input_tokens, u.output_tokens) == (0, 3)


def test_openai_chat_sse_zero_usage_complete():
    sse = (b'data: {"choices":[],"usage":{"prompt_tokens":0,"completion_tokens":0}}\n\n'
           b"data: [DONE]\n\n")
    u = _usage(sse, provider="openai")
    assert (u.input_tokens, u.output_tokens) == (0, 0)
    assert (u.source, u.status) == ("provider_reported", "complete")


def test_missing_usage_is_unavailable_not_zero():
    u = _usage(b'{"id":"msg_1","content":[]}')
    assert u.status == "unavailable"
    assert u.output_tokens is None
    assert u.source == "estimated"  # only the prompt estimate is shown, labelled as such
    assert u.cost_usd is None


def test_interrupted_anthropic_stream_keeps_known_input_and_marks_partial():
    sse = (b"event: message_start\n"
           b'data: {"type":"message_start","message":{"usage":{"input_tokens":42,"output_tokens":1}}}\n\n')
    u = _usage(sse)
    assert u.status == "partial"
    assert u.input_tokens == 42
    assert u.source == "provider_reported"


def test_ingress_block_is_estimate_with_no_upstream_consumption():
    u = _usage(None, decision="blocked", execution_status="blocked")
    assert u.status == "no_upstream"
    assert u.source == "estimated"
    assert u.output_tokens == 0 and u.input_tokens and u.cost_usd is None


def test_response_block_without_capture_is_unknown_not_no_upstream():
    """Upstream was dispatched (attempt recorded) but its body is gone:
    consumption is unknown, never 'no upstream' / zero."""
    u = _usage(None, decision="blocked", routing_meta={"attempts": [{"model": "m", "succeeded": True}]})
    assert u.status == "unavailable"
    assert u.output_tokens is None


def test_upstream_error_without_body_output_unknown():
    u = _usage(None, execution_status="error", routing_meta={"attempts": [{"succeeded": False}]})
    assert u.status == "unavailable" and u.output_tokens is None


def test_legacy_tuple_wrapper_unchanged():
    assert audit._audit_tokens_and_cost(
        provider="anthropic", model="claude-sonnet-4-6", body={},
        response_bytes=b'{"usage":{"input_tokens":1,"output_tokens":0}}',
        routing_meta=None, execution_status=None,
    )[:2] == (1, 0)


def test_client_reported_provenance():
    assert client_usage_provenance(None, None) == (None, None)  # no LLM usage invented
    assert client_usage_provenance(0, 0) == ("client_reported", "complete")
    assert client_usage_provenance(7, None) == ("client_reported", "partial")


def test_row_state_legacy_vs_known():
    assert _row_state(SimpleNamespace(usage_status=None)) == "legacy"
    assert _row_state(SimpleNamespace(usage_status="complete")) == "known"
    assert _row_state(SimpleNamespace(usage_status="pending")) == "pending"


def _attempt(ordinal, tin, tout, completeness="complete"):
    return AttemptEvidence(
        id=uuid4(), request_id=uuid4(), attempt_ordinal=ordinal, provider="anthropic", model="m",
        contract_version=1, pricing_version="v", normalizer_version="v1", currency="USD",
        usage_origin="provider_reported" if tin is not None else "missing",
        usage_completeness=completeness, pricing_completeness="priced",
        execution_outcome="succeeded", total_input_tokens=tin, total_output_tokens=tout,
        cache_read_tokens=None, reasoning_output_tokens=None, calculated_cost_microdollars=None,
    )


def test_fallback_totals_partial_when_an_attempt_is_unknown():
    totals = _totals([_attempt(0, None, None, "unavailable"), _attempt(1, 10, 0)],
                     request_count=1, missing_requests=0, coverage_complete=True)
    assert totals.input_tokens.value == 10 and totals.input_tokens.status == "partial"
    assert totals.output_tokens.value == 0 and totals.output_tokens.status == "partial"


def test_fallback_totals_complete_sums_each_attempt_once():
    totals = _totals([_attempt(0, 5, 0), _attempt(1, 10, 3)],
                     request_count=1, missing_requests=0, coverage_complete=True)
    assert (totals.input_tokens.value, totals.output_tokens.value) == (15, 3)
    assert totals.input_tokens.status == "complete"


def test_insert_accepted_is_pending_estimate(monkeypatch):
    db = Mock()
    monkeypatch.setattr(audit, "SessionLocal", lambda: db)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *a: None)
    audit.insert_accepted(str(uuid4()), "u", "codex", "openai", "m", body={"input": "hello there"},
                          request_id=str(uuid4()), agent_identity_id=str(uuid4()))
    stmt, params = db.execute.call_args.args
    assert "'pending'" in str(stmt)
    assert params["usage_source"] == "estimated"


def test_finalize_writes_provenance_and_replaces_estimate(monkeypatch):
    db = Mock()
    db.execute.return_value.rowcount = 1
    monkeypatch.setattr(audit, "SessionLocal", lambda: db)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *a: None)
    audit.finalize(str(uuid4()), str(uuid4()), decision="allowed", provider="anthropic",
                   model="claude-sonnet-4-6", body={},
                   response_bytes=json.dumps({"usage": {"input_tokens": 0, "output_tokens": 0}}).encode(),
                   duration_ms=1)
    stmt, params = db.execute.call_args.args
    assert "usage_status" in str(stmt) and "COALESCE(:tin" not in str(stmt)
    assert (params["tin"], params["tout"]) == (0, 0)
    assert (params["usage_source"], params["usage_status"]) == ("provider_reported", "complete")


def test_event_usage_detail_reports_row_and_attempt_totals(monkeypatch):
    from app.modules.guard import event_usage as eu
    from app.runtime.accounting.request_evidence import RequestUsage, RequestUsageBatch

    request_id = uuid4()
    attempts = [_attempt(0, None, None, "unavailable"), _attempt(1, 10, 0)]
    totals = _totals(attempts, request_count=1, missing_requests=0, coverage_complete=True)
    usage = RequestUsage(request_id, attempts, 2, 0, True, totals)
    monkeypatch.setattr(eu, "read_request_evidence",
                        lambda db, **kw: RequestUsageBatch({request_id: usage}, totals))
    event = SimpleNamespace(id=uuid4(), request_id=request_id, workspace_id=uuid4(),
                            agent_identity_id=None, tokens_before=10, tokens_after=0,
                            usage_source="provider_reported", usage_status="complete",
                            cost_usd_after=None)
    out = eu.event_usage(Mock(), event)
    assert out["row"]["output_tokens"] == 0 and out["row"]["state"] == "known"
    assert out["row"]["cost_usd"] is None
    assert out["totals"]["input_tokens"] == {"value": 10, "status": "partial"}
    assert len(out["attempts"]) == 2 and out["attempts"][0]["total_input_tokens"] is None


def test_usage_route_requires_permission_and_auth():
    from app.modules.guard.routers.events_query import router
    route = next(r for r in router.routes if r.path.endswith("/{event_id}/usage"))
    names = {d.call.__qualname__ for d in route.dependant.dependencies}
    # third dependency is the permission check (test conftest may stub its name)
    assert len(names - {"get_workspace_id", "get_user_id", "get_db"}) == 1
    assert "get_workspace_id" in names and "get_user_id" in names
