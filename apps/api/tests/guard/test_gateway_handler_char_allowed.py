"""#2399 characterization — allowed requests through ``handle_gateway_request``.

Pins today's behaviour (status/body/stream chunks, durable audit rows,
receipts, budget reserve + settle, admission ticket) for an allowed v2
request, streaming and non-streaming, plus the X-Request-Id
"idempotency" contract. See ``_gateway_handler_char_helpers`` for the
boundaries that are stubbed.
"""
from __future__ import annotations

import json

import pytest

from tests.guard._gateway_handler_char_helpers import (  # noqa: F401 — gw is a fixture
    CHAT, COND_MODEL, IDENTITY, MEMBER, PATH, PROFILE_ID, REVISION, SSE_CHUNKS, WS,
    audit_tasks, drain, gw, ok_sse,
)

_V2_META = {
    "gateway_version": "v2", "cond_code": "abcdefgh", "gateway_profile_id": PROFILE_ID,
    "gateway_profile": COND_MODEL, "revision_id": str(REVISION), "v2_operation": "openai_chat_completions",
}
_WINNER = [{"target_id": "t0", "transport": "native_http", "provider_or_integration": "openai",
            "succeeded": True, "error_class": None, "response_bytes_b64": None, "model": "gpt-4o",
            "operation": "openai_chat_completions"}]


def _stream_body():
    return {"model": COND_MODEL, "stream": True, "messages": [{"role": "user", "content": "hello"}]}


@pytest.mark.asyncio
async def test_allowed_non_streaming_happy_path(gw):
    response, background = await gw.call()

    # HTTP: upstream JSON passes through unchanged; server request id header added.
    assert response.status_code == 200
    assert json.loads(response.body) == CHAT
    request_id = response.headers["x-conduct-request-id"]

    # Upstream: one call, alias swapped for the target model.
    assert len(gw.sent) == 1
    assert str(gw.sent[0].url) == "https://api.openai.com/v1/chat/completions"
    assert json.loads(gw.sent[0].content)["model"] == "gpt-4o"
    assert gw.sent[0].headers["authorization"] == "Bearer fixture-vendor-key"

    # Policy: ingress prompt gate, per-target prompt re-eval, response gate — in that order.
    assert [c.gate for c in gw.policy_ctx] == ["prompt", "prompt", "response"]
    assert gw.policy_ctx[0].model == COND_MODEL and gw.policy_ctx[1].model == "gpt-4o"
    assert gw.policy_ctx[0].agent_identity_id == IDENTITY

    # Durable audit: one accepted row, one finalize, no legacy background record.
    assert len(gw.inserted) == 1
    accepted = gw.inserted[0]
    assert accepted.args == (WS, MEMBER, "unknown", "openai", COND_MODEL)
    assert accepted.kwargs["request_id"] == request_id
    assert accepted.kwargs["route"] == PATH
    assert accepted.kwargs["agent_identity_id"] == IDENTITY
    assert accepted.kwargs["user_email"] == "member@example.test"
    assert accepted.kwargs["routing_meta"] == {"operation": "/v1/chat/completions", **_V2_META}
    assert len(gw.finalized) == 1
    row = gw.finalized[0]
    assert row["row_id"] == "row-1" and row["workspace_id"] == WS
    assert (row["decision"], row["execution_status"], row["rule_id"]) == ("allowed", "ok", None)
    # Audit model is the cond alias, not the served target model (per-attempt
    # model lives in routing_meta.attempts).
    assert row["model"] == COND_MODEL
    assert json.loads(row["response_bytes"]) == CHAT
    # v2 coordinator overwrites routing_meta["operation"] (wire path -> v2 op).
    assert row["routing_meta"] == {**_V2_META, "operation": "openai_chat_completions",
                                   "winning_target_id": "t0", "attempt_count": 1, "attempts": _WINNER}
    assert audit_tasks(background) == []

    # Receipts written once, keyed by the same server request id.
    assert len(gw.receipts) == 1
    receipt = gw.receipts[0]
    assert receipt["request_id"] == request_id
    assert receipt["dispatched"] is True
    assert receipt["model"] == COND_MODEL and receipt["operation"] == PATH
    assert receipt["reserved_microdollars"] == 10_000
    assert receipt["attempts_meta"] == _WINNER
    assert json.loads(receipt["response_bytes"]) == CHAT

    # Budget: reserve once (keyed by request id), commit once with priced actuals.
    assert len(gw.ledger.reserve_calls) == 1
    reserve = gw.ledger.reserve_calls[0]
    assert reserve["request_id"] == request_id
    assert reserve["agent_identity_id"] == IDENTITY
    assert reserve["source"] == "gateway" and reserve["client_tool"] == "unknown"
    assert reserve["estimated_cents"] >= 1 and reserve["estimated_micros"] > 0
    assert gw.ledger.release_calls == []
    assert len(gw.ledger.commit_calls) == 1
    commit = gw.ledger.commit_calls[0]
    assert [r.reservation_id for r in commit["reservations"]] == ["res-0"]
    assert isinstance(commit["actual_micros"], int) and commit["actual_micros"] > 0
    assert commit["actual_cents"] == int(round(commit["actual_micros"] / 10_000))

    # Admission ticket released exactly once, never deferred.
    assert (gw.ticket.release_calls, gw.ticket.deferred) == (1, False)


@pytest.mark.asyncio
async def test_allowed_streaming_chunks_then_finalize_and_settle_on_drain(gw):
    gw.upstream = [ok_sse]
    response, background = await gw.call(_stream_body())

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/event-stream"
    request_id = response.headers["x-conduct-request-id"]

    # Before the body drains: row accepted, nothing finalized / settled /
    # receipted, admission deferred to the stream.
    assert len(gw.inserted) == 1
    assert gw.finalized == [] and gw.receipts == [] and gw.ledger.commit_calls == []
    assert gw.ticket.deferred is True and gw.ticket.release_calls == 0
    assert len(gw.ledger.reserve_calls) == 1

    body = await drain(response)
    assert body == b"".join(SSE_CHUNKS)
    assert json.loads(gw.sent[0].content) == {"model": "gpt-4o", "stream": True,
                                              "messages": [{"role": "user", "content": "hello"}]}

    # After drain: finalize with the raw SSE bytes, one receipt, one commit.
    assert len(gw.finalized) == 1
    row = gw.finalized[0]
    assert (row["decision"], row["execution_status"], row["rule_id"]) == ("allowed", "ok", None)
    assert row["response_bytes"] == b"".join(SSE_CHUNKS)
    assert row["routing_meta"]["attempts"] == _WINNER
    assert len(gw.receipts) == 1
    assert gw.receipts[0]["request_id"] == request_id
    assert gw.receipts[0]["response_bytes"] == b"".join(SSE_CHUNKS)
    assert gw.ledger.release_calls == []
    assert len(gw.ledger.commit_calls) == 1
    assert gw.ledger.commit_calls[0]["actual_micros"] > 0
    assert audit_tasks(background) == []
    # Policy order identical to non-streaming; response gate runs at end-of-stream.
    assert [c.gate for c in gw.policy_ctx] == ["prompt", "prompt", "response"]
    # SUSPECT: release() is called twice on the admission ticket — once by
    # ``_wrap_streaming_response(on_close=...)`` and once by
    # ``_wrap_v2_stream_finalize(on_close=...)``. The real ticket tolerates
    # it (``released`` guard), but it is a double hand-off.
    assert gw.ticket.release_calls == 2


@pytest.mark.asyncio
async def test_allowed_non_streaming_durable_audit_off_records_legacy_row(gw):
    """X2 path: v2 with durable audit OFF lands a single background ``record``."""
    gw.durable(False)
    response, background = await gw.call()

    assert response.status_code == 200
    request_id = response.headers["x-conduct-request-id"]
    assert gw.inserted == [] and gw.finalized == []
    tasks = audit_tasks(background)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.name == "record"
    assert task.args[:7] == (WS, MEMBER, "unknown", "openai", COND_MODEL, "allowed", None)
    assert task.kwargs["execution_status"] == "ok"
    assert task.kwargs["request_id"] == request_id
    assert task.kwargs["agent_identity_id"] == IDENTITY and task.kwargs["route"] == PATH
    assert task.kwargs["routing_meta"]["attempts"] == _WINNER
    # Accounting still keys on the minted request id with durable audit off.
    assert gw.receipts[0]["request_id"] == request_id
    assert gw.ledger.reserve_calls[0]["request_id"] == request_id
    assert len(gw.ledger.commit_calls) == 1


@pytest.mark.asyncio
async def test_same_client_request_id_is_not_deduplicated(gw):
    """Idempotent retry: NOT implemented. X-Request-Id is correlation only.

    Two requests with the same ``X-Request-Id`` both dispatch upstream,
    each gets a fresh server-minted request id, reservation and receipt.
    The client id is recorded on routing_meta.client_request_id.
    """
    headers = {"x-request-id": "client-retry-1"}
    first, _ = await gw.call(headers=headers)
    second, _ = await gw.call(headers=headers)

    assert first.status_code == second.status_code == 200
    assert len(gw.sent) == 2
    ids = [first.headers["x-conduct-request-id"], second.headers["x-conduct-request-id"]]
    assert ids[0] != ids[1] and "client-retry-1" not in ids
    assert [i.kwargs["request_id"] for i in gw.inserted] == ids
    assert [i.kwargs["routing_meta"]["client_request_id"] for i in gw.inserted] == ["client-retry-1"] * 2
    assert [f["routing_meta"]["client_request_id"] for f in gw.finalized] == ["client-retry-1"] * 2
    assert [r["request_id"] for r in gw.ledger.reserve_calls] == ids
    assert [r["request_id"] for r in gw.receipts] == ids
    assert len(gw.ledger.commit_calls) == 2


@pytest.mark.asyncio
async def test_attribution_headers_flow_to_audit_and_receipts(gw):
    run_id = "66666666-6666-4666-8666-666666666666"
    response, _ = await gw.call(headers={
        "x-conductai-run-id": run_id, "x-conductai-workflow": "wf", "x-conductai-workflow-id": "wf-1",
        "x-conduct-session-id": "sess-1", "x-conduct-ai-tool": "cursor",
    })
    assert response.status_code == 200
    accepted = gw.inserted[0]
    assert accepted.args[2] == "cursor"
    assert (accepted.kwargs["conductai_run_id"], accepted.kwargs["conductai_workflow"],
            accepted.kwargs["conductai_workflow_id"], accepted.kwargs["hook_session_id"]) == (
        run_id, "wf", "wf-1", "sess-1")
    assert str(gw.receipts[0]["workflow_run_id"]) == run_id
    assert gw.receipts[0]["hook_session_id"] == "sess-1"
    assert gw.receipts[0]["client_tool"] == "cursor"
    assert gw.ledger.reserve_calls[0]["client_tool"] == "cursor"
