"""#2403 items 3-6 — fallback settlement, all-targets-failed accounting,
hang fallback, served-model attribution."""
from __future__ import annotations

import asyncio
import json
import time

import httpx
import pytest
from fastapi import HTTPException

from tests.guard._gateway_handler_char_helpers import (  # noqa: F401 — gw is a fixture
    COND_MODEL, SSE_CHUNKS, audit_tasks, drain, gw, ok_json, ok_sse, profile, status,
)


def _status_with_usage(code: int):
    """Provider error envelope that still reports billed usage."""
    body = {"error": {"message": "fixture", "type": "fixture"},
            "usage": {"prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5}}
    return lambda request: httpx.Response(code, json=body)


async def _raises(gw) -> HTTPException:
    with pytest.raises(HTTPException) as excinfo:
        await gw.call()
    return excinfo.value


# ── item 3: success after fallback (deliberate: reconciler owns it) ──────


@pytest.mark.asyncio
async def test_fallback_success_with_unpriceable_failed_attempt_leaves_reservation_open(gw):
    """Deliberate (#2209 PR 4, accounting invariant "known zero is not
    missing usage"): a failed attempt whose cost is unknown keeps the
    reservation open for the recovery sweep. Neither commit (would be a
    lower bound) nor release (would drop possibly-billed spend)."""
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(503), ok_json]
    response, _ = await gw.call()
    assert response.status_code == 200
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []
    # Both attempts reach the receipt so the sweep can classify from them.
    assert [a["succeeded"] for a in gw.receipts[0]["attempts_meta"]] == [False, True]


@pytest.mark.asyncio
async def test_fallback_success_with_priced_failed_attempt_settles_live(gw):
    """When every attempt is priceable the live path commits the sum."""
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [_status_with_usage(503), ok_json]
    response, _ = await gw.call()
    assert response.status_code == 200
    assert len(gw.ledger.commit_calls) == 1
    assert gw.ledger.commit_calls[0]["actual_micros"] > 0


# ── item 4: all targets failing ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_all_targets_failed_records_attempts_on_audit_and_receipts(gw):
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(503)]
    exc = await _raises(gw)
    assert exc.status_code == 502
    attempts = gw.finalized[0]["routing_meta"]["attempts"]
    assert [(a["target_id"], a["model"], a["succeeded"]) for a in attempts] == [
        ("t0", "gpt-4o", False), ("t1", "gpt-4o-mini", False)]
    assert gw.finalized[0]["routing_meta"]["attempt_count"] == 2
    receipt = gw.receipts[0]
    assert [a["target_id"] for a in receipt["attempts_meta"]] == ["t0", "t1"]
    # No usage on the error envelopes: unknown cost, reservation stays open.
    assert gw.ledger.commit_calls == [] and gw.ledger.release_calls == []


@pytest.mark.asyncio
async def test_all_targets_failed_with_billed_usage_is_priced_and_settled(gw):
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [_status_with_usage(503)]
    exc = await _raises(gw)
    assert exc.status_code == 502
    assert len(gw.receipts[0]["attempts_meta"]) == 2
    assert len(gw.ledger.commit_calls) == 1
    assert gw.ledger.commit_calls[0]["actual_micros"] > 0


@pytest.mark.asyncio
async def test_all_targets_failed_durable_off_record_carries_attempts(gw):
    gw.durable(False)
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(503)]
    recorded = []
    gw.monkeypatch.setattr("app.guard.audit.record", lambda *a, **k: recorded.append((a, k)))
    await _raises(gw)
    assert len(recorded) == 1
    assert len(recorded[0][1]["routing_meta"]["attempts"]) == 2


# ── item 5: hung target falls back ───────────────────────────────────────


@pytest.mark.asyncio
async def test_hung_target_falls_back_within_profile_deadline(gw):
    async def _hang(request):
        await asyncio.sleep(30)

    gw.set_profile(profile("gpt-4o", "gpt-4o-mini", timeout_seconds=2))
    gw.upstream = [lambda request: _hang(request), ok_json]
    started = time.monotonic()
    response, _ = await gw.call()
    assert response.status_code == 200
    assert time.monotonic() - started < 2
    assert [json.loads(r.content)["model"] for r in gw.sent] == ["gpt-4o", "gpt-4o-mini"]
    attempts = gw.finalized[0]["routing_meta"]["attempts"]
    assert [(a["target_id"], a["error_class"]) for a in attempts] == [
        ("t0", "TimeoutError"), ("t1", None)]


# ── item 6: served-model attribution ─────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_and_receipt_record_served_model_alias_kept(gw):
    gw.set_profile(profile("gpt-4o", "gpt-4o-mini"))
    gw.upstream = [status(503), ok_json]
    await gw.call()
    row = gw.finalized[0]
    assert row["model"] == "gpt-4o-mini"
    assert row["routing_meta"]["gateway_profile"] == COND_MODEL
    receipt = gw.receipts[0]
    assert receipt["model"] == "gpt-4o-mini"
    assert receipt["model_alias"] == COND_MODEL


@pytest.mark.asyncio
async def test_streaming_finalize_records_served_model(gw):
    gw.upstream = [ok_sse]
    response, _ = await gw.call({"model": COND_MODEL, "stream": True,
                                 "messages": [{"role": "user", "content": "hello"}]})
    assert await drain(response) == b"".join(SSE_CHUNKS)
    assert gw.finalized[0]["model"] == "gpt-4o"
    assert gw.receipts[0]["model_alias"] == COND_MODEL


@pytest.mark.asyncio
async def test_durable_off_record_uses_served_model(gw):
    gw.durable(False)
    response, background = await gw.call()
    assert response.status_code == 200
    assert audit_tasks(background)[0].args[4] == "gpt-4o"


def test_finalize_writes_model_column(monkeypatch):
    from app.guard import audit

    executed = []

    class _Result:
        rowcount = 1

    class _Session:
        def execute(self, stmt, params=None):
            executed.append((str(stmt), params))
            return _Result()

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(audit, "SessionLocal", _Session)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *a, **k: None)
    audit.finalize("00000000-0000-0000-0000-000000000001", "ws", decision="allowed",
                   provider="openai", model="gpt-4o-mini", body={}, response_bytes=None,
                   duration_ms=1)
    sql, params = executed[-1]
    assert "model" in sql.split("SET", 1)[1].split("WHERE", 1)[0]
    assert params["model"] == "gpt-4o-mini"
