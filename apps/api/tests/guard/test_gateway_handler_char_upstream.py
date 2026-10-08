"""#2399 characterization — upstream failures in ``handle_gateway_request``.

v2: the REAL ``AttemptCoordinator`` walks profile targets; vendor HTTP is the
only fake. Pins retry/fallback classification, the status the client sees,
the durable-audit outcome, receipts and settlement for 5xx, 4xx, transport
timeouts and the profile deadline. v1 (legacy ``transport.forward``) is pinned
for the happy path and an upstream 5xx (no retry).
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from tests.guard._gateway_handler_char_helpers import (  # noqa: F401 — gw is a fixture
    CHAT, COND_MODEL, PATH, WS, audit_tasks, gw, ok_json, profile, raises, status,
)


async def _call_raises(gw) -> HTTPException:
    with pytest.raises(HTTPException) as excinfo:
        await gw.call()
    return excinfo.value


def _attempt_errors(row) -> list:
    return [(a["target_id"], a["succeeded"], a["error_class"]) for a in row["routing_meta"]["attempts"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("first", [
    status(503),
    raises(lambda r: httpx.ReadTimeout("slow", request=r)),
    raises(lambda r: httpx.ConnectError("refused", request=r)),
])
async def test_transient_failure_falls_back_to_next_target(gw, first):
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [first, ok_json]

    response, background = await gw.call()

    assert response.status_code == 200
    assert json.loads(response.body) == CHAT
    assert [json.loads(r.content)["model"] for r in gw.sent] == ["gpt-4o", "gpt-4o-mini"]
    row = gw.finalized[0]
    assert (row["decision"], row["execution_status"]) == ("allowed", "ok")
    assert row["routing_meta"]["winning_target_id"] == "t1"
    assert row["routing_meta"]["attempt_count"] == 2
    assert [e[:2] for e in _attempt_errors(row)] == [("t0", False), ("t1", True)]
    # Per-target policy re-eval runs once per dispatched target.
    assert [c.gate for c in gw.policy_ctx] == ["prompt", "prompt", "prompt", "response"]
    assert len(gw.receipts) == 1
    assert len(gw.receipts[0]["attempts_meta"]) == 2
    # The failed attempt carries no priceable usage, so strict settlement
    # returns None -> PENDING_RECONCILER: neither commit nor release.
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    assert audit_tasks(background) == []
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_all_targets_5xx_raises_502_and_finalizes_error(gw):
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(503)]

    exc = await _call_raises(gw)

    assert exc.status_code == 502
    assert exc.detail.startswith(f"All Gateway v2 targets failed for revision {gw.plan.resolved.revision_id}")
    assert "t0=HTTPStatusError; t1=HTTPStatusError" in exc.detail
    assert len(gw.sent) == 2
    assert len(gw.finalized) == 1
    row = gw.finalized[0]
    assert (row["decision"], row["execution_status"], row["rule_id"]) == ("error", "error", None)
    assert row["result_summary"].startswith("forward/gate exception: HTTPException: 502: All Gateway v2 targets failed")
    assert row["response_bytes"] is None
    # SUSPECT: the coordinator's attempt list (plan.last_meta) is NOT merged
    # into routing_meta on the raise path, so the finalized row and the
    # receipt lose per-attempt records even though two targets were hit.
    assert "attempts" not in row["routing_meta"]
    assert gw.plan.last_meta["attempt_count"] == 2
    assert len(gw.receipts) == 1
    receipt = gw.receipts[0]
    assert (receipt["dispatched"], receipt["response_bytes"], receipt["attempts_meta"]) == (True, None, None)
    # Dispatched with unknown cost -> reservation left for the reconciler.
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_hang_past_profile_deadline_is_502_without_fallback(gw):
    """A hang consumes the whole profile deadline; the fallback target is never dispatched."""
    async def _hang(request):
        await asyncio.sleep(30)

    gw.set_profile(profile("gpt-4o", "gpt-4o-mini", timeout_seconds=1))
    gw.upstream = [lambda request: _hang(request), ok_json]

    exc = await _call_raises(gw)

    assert exc.status_code == 502
    assert "t0=TimeoutError" in exc.detail
    assert len(gw.sent) == 1
    assert [(a["target_id"], a["error_class"]) for a in gw.plan.last_meta["attempts"]] == [
        ("t0", "TimeoutError"), ("t1", "DeadlineExceeded")]
    assert gw.finalized[0]["decision"] == "error"
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("code,expected", [(400, 400), (401, 424), (403, 424), (429, 429)])
async def test_upstream_4xx_classification(gw, code, expected):
    """4xx are permanent (no fallback) except 429, which falls back and then
    surfaces the last provider status; 401/403 surface as 424."""
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(code, "fixture refusal")]

    exc = await _call_raises(gw)

    assert exc.status_code == expected
    assert len(gw.sent) == (2 if code == 429 else 1)
    if code == 400:
        assert exc.detail == ("Provider openai rejected the request for target 't0' on Gateway profile "
                              "'fixture-profile' (HTTP 400): fixture refusal")
    if code in (401, 403):
        assert "rejected the credential" in exc.detail and "fixture refusal" not in exc.detail
    assert gw.finalized[0]["decision"] == "error"
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []


# ── v1 (legacy transport.forward) ───────────────────────────────────────


@pytest.fixture
def v1(gw, monkeypatch):
    monkeypatch.setattr("app.modules.guard.gateway_helpers._resolve_upstream_credentials",
                        lambda *a: ("https://api.openai.com", None, "fixture-vault-key"))
    from app.modules.guard.circuit_breaker import get_breaker
    get_breaker().record_success("openai")
    return gw


_V1_BODY = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]}


@pytest.mark.asyncio
async def test_v1_non_streaming_happy_path(v1):
    response, background = await v1.call(dict(_V1_BODY))

    assert response.status_code == 200
    assert json.loads(response.body) == CHAT
    request_id = response.headers["x-conduct-request-id"]
    assert len(v1.sent) == 1
    assert str(v1.sent[0].url) == "https://api.openai.com/v1/chat/completions"
    assert v1.sent[0].headers["authorization"] == "Bearer fixture-vault-key"
    assert [c.gate for c in v1.policy_ctx] == ["prompt", "response"]
    # Durable row opened inline; v1 finalize is a queued background task.
    assert len(v1.inserted) == 1
    assert v1.inserted[0].kwargs["routing_meta"] == {"operation": "/v1/chat/completions"}
    assert v1.finalized == []
    tasks = audit_tasks(background)
    assert len(tasks) == 1
    assert tasks[0].name == "finalize"
    assert tasks[0].args == ("row-1", WS)
    assert (tasks[0].kwargs["decision"], tasks[0].kwargs["execution_status"]) == ("allowed", "success")
    assert json.loads(tasks[0].kwargs["response_bytes"]) == CHAT
    assert len(v1.receipts) == 1
    assert v1.receipts[0]["request_id"] == request_id and v1.receipts[0]["attempts_meta"] is None
    assert len(v1.ledger.commit_calls) == 1
    assert v1.ledger.commit_calls[0]["actual_micros"] > 0
    assert v1.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_v1_upstream_5xx_passes_through_without_retry(v1):
    v1.upstream = [status(500, "boom")]

    response, background = await v1.call(dict(_V1_BODY))

    assert response.status_code == 500
    assert json.loads(response.body) == {"error": {"message": "boom", "type": "fixture"}}
    assert len(v1.sent) == 1
    tasks = audit_tasks(background)
    assert len(tasks) == 1 and tasks[0].name == "finalize"
    assert (tasks[0].kwargs["decision"], tasks[0].kwargs["execution_status"],
            tasks[0].kwargs["result_summary"]) == ("allowed", "error", "Upstream HTTP 500")
    # Error body has no usage -> unpriced -> reservation left for the reconciler.
    assert v1.ledger.commit_calls == [] and v1.ledger.release_calls == []
    assert len(v1.receipts) == 1
