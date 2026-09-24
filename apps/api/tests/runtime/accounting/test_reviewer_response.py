"""Session 6c reviewer-response self-checks.

Pins the specific fixes for the 9 findings on #2221 so any regression
surfaces at the exact bug that caused it.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.contracts import (
    ExecutionOutcome,
    PricingCompleteness,
    UsageCompleteness,
)


@pytest.fixture
def _shadow_on():
    # Cutover: writer always on. Fixture kept as a no-op for existing callers.
    yield


@pytest.fixture
def _captured_rows(monkeypatch):
    captured: list = []
    def _capture(_db, row, *, is_reconciler):
        captured.append(row)
        return row.id
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    return captured


# ─── Finding #1: developer_external_id accepts non-UUID identifiers ─────────


def test_clerk_id_no_longer_drops_receipt(_shadow_on, _captured_rows):
    """Passing 'user_2abcXYZ' or 'system:lens' used to fail the UUID cast
    and silently drop the whole receipt. Now the row is written with the
    identifier landing in developer_external_id."""
    from app.runtime.accounting.shadow_writer import shadow_write

    for external in ("user_2abcXYZ", "system:lens", "someone@example.com"):
        rid = shadow_write(
            workspace_id=uuid.uuid4(),
            request_id=uuid.uuid4(),
            provider="anthropic",
            model="claude-sonnet-4-6",
            operation="messages.create",
            dispatched=True,
            response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
            legacy_input_tokens=10,
            legacy_output_tokens=5,
            legacy_cost_usd=0.0001,
            developer_user_id=external,  # legacy call site: passes non-UUID
        )
        assert rid is not None
    assert len(_captured_rows) == 3
    externals = [r.developer_external_id for r in _captured_rows]
    assert externals == ["user_2abcXYZ", "system:lens", "someone@example.com"]
    assert all(r.developer_user_id is None for r in _captured_rows)


def test_real_uuid_still_lands_in_developer_user_id(_shadow_on, _captured_rows):
    from app.runtime.accounting.shadow_writer import shadow_write

    user_uuid = uuid.uuid4()
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
        developer_user_id=user_uuid,
    )
    row = _captured_rows[0]
    assert row.developer_user_id == user_uuid
    assert row.developer_external_id is None


# ─── Finding #3: per-attempt receipts via helper ─────────────────────────────


def test_write_receipts_for_attempts_writes_one_per_attempt(_shadow_on, _captured_rows):
    """Multi-attempt request produces N receipts, one per attempt in
    attempts_meta. Failed attempts marked FAILED; winner marked SUCCEEDED."""
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    attempts_meta = [
        {"provider_or_integration": "anthropic", "succeeded": False, "error_class": "RateLimit"},
        {"provider_or_integration": "openai", "succeeded": True},
    ]
    rids = write_receipts_for_attempts(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
        attempts_meta=attempts_meta,
    )
    assert len(rids) == 2
    assert len(_captured_rows) == 2
    assert _captured_rows[0].attempt_ordinal == 0
    assert _captured_rows[0].execution_outcome == ExecutionOutcome.FAILED.value
    assert _captured_rows[0].provider == "anthropic"
    assert _captured_rows[1].attempt_ordinal == 1
    assert _captured_rows[1].execution_outcome == ExecutionOutcome.SUCCEEDED.value
    assert _captured_rows[1].provider == "openai"
    # Chain
    assert _captured_rows[1].parent_receipt_id == _captured_rows[0].id


def test_write_receipts_for_attempts_falls_back_to_single_when_no_meta(
    _shadow_on, _captured_rows
):
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    rids = write_receipts_for_attempts(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
        attempts_meta=None,
    )
    assert len(rids) == 1
    assert _captured_rows[0].attempt_ordinal == 0


# ─── Finding #4: cache pricing double-subtract (reviewer's exact repro) ─────


def test_reviewer_pricing_repro_no_double_subtract():
    """Sudhi's exact repro: 100 fresh + 900 cache reads + 200 output at
    claude-sonnet-4-6 rates = 3_570 microdollars (was 3_270 before fix)."""
    from app.runtime.accounting.pricing import PricingService

    result = PricingService().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=100,
        cache_read_tokens=900,
        output_tokens=200,
    )
    assert result.microdollars == 3_570


# ─── Finding #7: strict pricing surfaces UNPRICED for unknown models ────────


def test_shadow_writer_unknown_model_reports_unpriced(_shadow_on, _captured_rows):
    """Legacy silent-fallback contaminated shadow comparison. Writer now uses
    strict=True; unknown model → UNPRICED, no calculated cost."""
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-unknown-model-9000",  # not in registry
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        legacy_input_tokens=100,
        legacy_output_tokens=50,
        legacy_cost_usd=0.0009,
    )
    row = _captured_rows[0]
    assert row.pricing_completeness == PricingCompleteness.UNPRICED.value
    assert row.calculated_cost_microdollars is None
    # Legacy comparison column still populated (untouched by strict flip)
    assert row.legacy_cost_microdollars == 900


# ─── Finding #8: Anthropic empty usage dict → UNAVAILABLE ───────────────────


def test_anthropic_empty_usage_dict_is_unavailable():
    """Empty usage {} used to be marked COMPLETE with zero input, silently
    conflating missing usage with reported zero."""
    from app.runtime.accounting import normalize_json, ProviderFamily

    result = normalize_json(ProviderFamily.ANTHROPIC_MESSAGES, {"usage": {}})
    assert result.completeness is UsageCompleteness.UNAVAILABLE


def test_anthropic_explicit_zero_still_complete():
    """{"usage": {"input_tokens": 0, "output_tokens": 0}} is legitimate zero,
    not missing. Invariant #4 preserved."""
    from app.runtime.accounting import normalize_json, ProviderFamily

    result = normalize_json(
        ProviderFamily.ANTHROPIC_MESSAGES,
        {"usage": {"input_tokens": 0, "output_tokens": 0}},
    )
    assert result.completeness is UsageCompleteness.COMPLETE
    assert result.tokens.total_output_tokens == 0


def test_shadow_writer_explicit_execution_outcome_wins(_shadow_on, _captured_rows):
    """Caller can pass execution_outcome directly. Writer no longer infers
    it from usage_completeness (which conflated concepts)."""
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=None,  # would default to FAILED
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
        execution_outcome=ExecutionOutcome.DISCONNECTED.value,
    )
    assert _captured_rows[0].execution_outcome == ExecutionOutcome.DISCONNECTED.value


# ─── Finding #9b: estimator covers tool-call args + max_output_tokens ───────


def test_estimator_counts_openai_tool_call_arguments():
    from app.runtime.accounting.estimator import InputShape, estimate_tokens

    body_no_tools = {"messages": [{"role": "user", "content": "hi"}]}
    body_with_tools = {
        "messages": [
            {"role": "user", "content": "hi"},
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "function": {
                            "name": "long_search",
                            "arguments": '{"query": "' + "x" * 400 + '"}',
                        }
                    }
                ],
            },
        ]
    }
    base = estimate_tokens(body_no_tools, include=frozenset([InputShape.MESSAGES]))
    with_tools = estimate_tokens(body_with_tools, include=frozenset([InputShape.MESSAGES]))
    assert with_tools.input_tokens > base.input_tokens


def test_estimator_counts_anthropic_tool_use_input():
    from app.runtime.accounting.estimator import InputShape, estimate_tokens

    body = {
        "messages": [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "reasoning"},
                    {"type": "tool_use", "id": "x", "name": "look", "input": {"q": "y" * 400}},
                ],
            }
        ]
    }
    result = estimate_tokens(body, include=frozenset([InputShape.MESSAGES]))
    # 400+ chars from tool_use.input serialized as JSON
    assert result.input_tokens > 100


def test_estimator_recognizes_max_output_tokens_responses_api():
    from app.runtime.accounting.estimator import estimate_tokens

    body_chat = {"max_tokens": 12345}
    body_responses = {"max_output_tokens": 6789}
    body_default = {}
    assert estimate_tokens(body_chat).output_tokens_allowance == 12345
    assert estimate_tokens(body_responses).output_tokens_allowance == 6789
    assert estimate_tokens(body_default).output_tokens_allowance == 4096
