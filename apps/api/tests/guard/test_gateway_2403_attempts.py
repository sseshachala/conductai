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
