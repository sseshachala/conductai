"""Session 6J self-checks — pins the fixes for the 7 findings on bbcb5388."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.contracts import (
    PricingCompleteness,
    UsageCompleteness,
)

@pytest.fixture
def _shadow_on():
    # Cutover: writer always on. Fixture kept as a no-op for existing callers.
    yield

# ─── #1 shadow_write returns the persisted ID (not a fresh UUID) ────────

def test_shadow_write_returns_persisted_id_from_persist_atomic(
    _shadow_on, monkeypatch
):
    """Reviewer #1 (#2221 review at bbcb5388): the persisted ID from
    _persist_atomic MUST match what shadow_write returns. Previously
    the writer generated a fresh UUID that never made it to disk under
    promotion or DO NOTHING."""
    from app.runtime.accounting.shadow_writer import shadow_write

    fake_persisted = uuid.uuid4()
    def _persist(_db, _row, *, is_reconciler):
        return fake_persisted

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _persist
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )

    got = shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',

    )
    assert got == fake_persisted

def test_shadow_write_returns_none_on_upsert_noop(_shadow_on, monkeypatch):
    """When _persist_atomic returns None (real row already existed, or
    reconciler DO NOTHING), shadow_write MUST return None so callers do
    not chain parent_receipt_id to a nonexistent row."""
    from app.runtime.accounting.shadow_writer import shadow_write

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic",
        lambda *_a, **_kw: None,
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    got = shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=None,

        source="reconciler",
    )
    assert got is None

def test_persist_atomic_uses_returning_clause():
    """Pin the SQL construction so a future refactor cannot drop the
    RETURNING clause and reintroduce the fresh-UUID bug."""
    import inspect
    from app.runtime.accounting import shadow_writer

    src = inspect.getsource(shadow_writer._persist_atomic)
    assert "stmt.returning" in src or ".returning(" in src

# ─── #2 keyset pagination ───────────────────────────────────────────────

def test_reconcile_result_carries_next_cursor():
    """ReconciliationResult exposes ``next_cursor`` so ops can loop
    through a period without stalling on the earliest 1000 rows."""
    from dataclasses import fields
    from app.runtime.accounting import ReconciliationResult

    names = {f.name for f in fields(ReconciliationResult)}
    assert "next_cursor" in names

def test_reconciler_fetch_uses_keyset_pagination():
    """Pin the (ts, request_id) tuple comparison — cursor semantics
    would break silently if a future refactor moved back to
    OFFSET-based pagination."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler._fetch_audit_rows)
    assert "(gae.ts, gae.request_id) > (:cursor_ts, :cursor_rid)" in src
    # ORDER BY must include request_id for the tuple compare to be
    # deterministic when two rows share a ts.
    assert "ORDER BY gae.ts ASC, gae.request_id ASC" in src

def test_reconcile_next_cursor_none_when_period_exhausted(monkeypatch):
    """When the scan returns fewer rows than the limit, next_cursor is
    None to signal 'end of period'."""
    from app.runtime.accounting import reconcile_missing_receipts

    session = MagicMock()
    session.execute.return_value.all.return_value = []
    monkeypatch.setattr(
        "app.runtime.accounting.reconciler.SessionLocal",
        MagicMock(return_value=session),
    )
    now = datetime.now(timezone.utc)
    result = reconcile_missing_receipts(
        workspace_id=str(uuid.uuid4()),
        period_start=now - timedelta(hours=1),
        period_end=now,
    )
    assert result.next_cursor is None

# ─── #3 cache-write tier pricing ────────────────────────────────────────

def test_pricing_uses_per_tier_rate_when_declared():
    """Reviewer #3 (#2221 review at bbcb5388): each cache-write tier is
    priced at its own rate when the pricing snapshot declares one."""
    from app.runtime.accounting.pricing import PricingService, RateCard

    # Manually build a service with a rate card that has tiered writes.
    svc = PricingService(
        pricing_snapshot={
            "version": "test",
            "providers": {
                "anthropic": {
                    "claude-sonnet-4-6": {
                        "input": 3.0,
                        "output": 15.0,
                        "cache_read": 0.30,
                        "cache_write": 3.75,  # single-tier fallback
                        "cache_write_by_tier": {
                            "ephemeral_5m": 3.75,
                            "ephemeral_1h": 6.00,
                        },
                    }
                }
            },
        }
    )
    # 1000 tokens in ephemeral_5m at $3.75/1M = $0.00375 = 3_750 μUSD
    # 1000 tokens in ephemeral_1h at $6.00/1M = $0.006   = 6_000 μUSD
    # Total = 9_750 μUSD (plus 0 for other buckets).
    result = svc.price_tokens(
        "anthropic",
        "claude-sonnet-4-6",
        uncached_input_tokens=0,
        output_tokens=0,
        cache_write_tokens_by_tier={
            "ephemeral_5m": 1000,
            "ephemeral_1h": 1000,
        },
    )
    assert result.microdollars == 9_750

def test_unknown_cache_write_tier_marks_incomplete_pricing_under_strict():
    """Reviewer #3: unknown tiers MUST NOT silently take the single-tier
    default rate under strict mode. Cost stays a lower bound and
    pricing_completeness downgrades to INCOMPLETE."""
    from app.runtime.accounting.pricing import PricingService

    svc = PricingService(
        pricing_snapshot={
            "version": "test",
            "providers": {
                "anthropic": {
                    "claude-sonnet-4-6": {
                        "input": 3.0,
                        "output": 15.0,
                        "cache_read": 0.30,
                        "cache_write": 3.75,
                        "cache_write_by_tier": {"ephemeral_5m": 3.75},
                    }
                }
            },
        }
    )
    result = svc.price_tokens(
        "anthropic",
        "claude-sonnet-4-6",
        uncached_input_tokens=100,
        output_tokens=50,
        cache_write_tokens_by_tier={
            "ephemeral_5m": 1000,
            "unknown_tier_9000": 500,
        },
        strict=True,
    )
    assert result.completeness is PricingCompleteness.INCOMPLETE
    # The unknown tier's tokens are excluded from the cost (0 rate),
    # so the cost is a lower bound.
    provenance_tiers = result.provenance.get("cache_write_tiers", {})
    assert "tier_unknown_tier_9000_unpriced" in provenance_tiers

def test_writer_passes_tier_breakdown_to_pricing():
    """Pin the writer's call so the tier breakdown reaches PricingService
    instead of being summed away."""
    import inspect
    from app.runtime.accounting import shadow_writer

    src = inspect.getsource(shadow_writer._shadow_write_impl)
    assert "cache_write_tokens_by_tier" in src

# ─── #4 developer_external_id in DEVELOPER scope ────────────────────────

def test_developer_scope_coalesces_external_id_when_uuid_null():
    """Reviewer #4 (#2221 review at bbcb5388): DEVELOPER scope must
    include external IDs — Gateway passes Clerk IDs into
    developer_external_id since they aren't UUIDs. Grouping on
    developer_user_id alone collapsed them into NULL."""
    import inspect
    from app.runtime.accounting.reader import _scope_column

    src = inspect.getsource(_scope_column)
    assert "coalesce" in src.lower()
    assert "developer_external_id" in src

# ─── #5 original operation preserved via routing_meta ───────────────────

def test_extract_operation_from_meta_returns_string_when_present():
    from app.runtime.accounting.reconciler import _extract_operation_from_meta

    assert (
        _extract_operation_from_meta({"operation": "/v1/responses"})
        == "/v1/responses"
    )

def test_extract_operation_from_meta_handles_missing_and_malformed():
    from app.runtime.accounting.reconciler import _extract_operation_from_meta

    assert _extract_operation_from_meta(None) is None
    assert _extract_operation_from_meta({}) is None
    assert _extract_operation_from_meta({"operation": ""}) is None
    assert _extract_operation_from_meta({"operation": 42}) is None
    assert _extract_operation_from_meta("garbage{{") is None

def test_write_placeholder_preserves_original_operation(monkeypatch):
    """The reconciler passes the original operation through so the
    normalizer picks the right family (Chat vs Responses)."""
    from app.runtime.accounting.reconciler import _write_placeholder
    from types import SimpleNamespace

    calls: list = []
    def _fake_shadow_write(**kw):
        calls.append(kw)
        return uuid.uuid4()
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.shadow_write", _fake_shadow_write
    )
    audit_row = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="openai",
        model="gpt-5",
        clerk_user_id="user_x",
        ai_tool="test",
        tokens_after=10,
        cost_usd_after=0.001,
        audit_ts=datetime.now(timezone.utc),
    )
    _write_placeholder(
        audit_row, 0, {"succeeded": True},
        original_operation="/v1/responses",
    )
    assert calls[0]["operation"] == "/v1/responses"

def test_write_placeholder_falls_back_to_reconciled_when_no_operation(monkeypatch):
    """Legacy audit rows written before Session 6J don't have
    routing_meta.operation. Fallback string is 'reconciled'."""
    from app.runtime.accounting.reconciler import _write_placeholder
    from types import SimpleNamespace

    calls: list = []
    def _fake_shadow_write(**kw):
        calls.append(kw)
        return uuid.uuid4()
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.shadow_write", _fake_shadow_write
    )
    audit_row = SimpleNamespace(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        clerk_user_id="user_x",
        ai_tool="test",
        tokens_after=10,
        cost_usd_after=0.001,
        audit_ts=datetime.now(timezone.utc),
    )
    _write_placeholder(audit_row, 0, {"succeeded": True}, original_operation=None)
    assert calls[0]["operation"] == "reconciled"

def test_gateway_handler_stores_operation_in_routing_meta():
    """Pin the gateway_handler write so future refactors don't drop the
    operation field from routing_meta. Both success + failure paths
    write ``"operation": plan.operation`` — pinned via source-string
    match so the presence isn't lost silently."""
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    assert src.count('"operation": plan.operation') >= 2

# ─── #7 OpenAI empty usage → UNAVAILABLE ────────────────────────────────

def test_openai_chat_empty_usage_dict_is_unavailable():
    from app.runtime.accounting import normalize_json, ProviderFamily

    result = normalize_json(ProviderFamily.OPENAI_CHAT, {"usage": {}})
    assert result.completeness is UsageCompleteness.UNAVAILABLE

def test_openai_responses_empty_usage_dict_is_unavailable():
    from app.runtime.accounting import normalize_json, ProviderFamily

    result = normalize_json(ProviderFamily.OPENAI_RESPONSES, {"usage": {}})
    assert result.completeness is UsageCompleteness.UNAVAILABLE

def test_openai_chat_explicit_zero_still_complete():
    """Reported zero is legitimate (invariant #4) — completeness stays
    COMPLETE, matching the Session 6F Anthropic fix."""
    from app.runtime.accounting import normalize_json, ProviderFamily

    result = normalize_json(
        ProviderFamily.OPENAI_CHAT,
        {"usage": {"prompt_tokens": 0, "completion_tokens": 0}},
    )
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_input_tokens == 0
