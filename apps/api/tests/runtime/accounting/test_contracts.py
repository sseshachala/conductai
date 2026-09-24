"""Session 1 contract self-checks. Guards the shape future sessions bind to."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal
from uuid import uuid4

import pytest

from app.runtime.accounting import (
    CONTRACT_VERSION,
    AttemptIdentity,
    Attribution,
    ExecutionOutcome,
    PricingCompleteness,
    TokenBreakdown,
    UsageCompleteness,
    UsageOrigin,
    UsageRecord,
    microdollars_from_usd,
    usd_from_microdollars,
)


def _minimal_record(**overrides) -> UsageRecord:
    workspace_id = uuid4()
    request_id = uuid4()
    receipt_id = uuid4()
    base = dict(
        contract_version=CONTRACT_VERSION,
        identity=AttemptIdentity(
            receipt_id=receipt_id,
            request_id=request_id,
            attempt_ordinal=0,
        ),
        attribution=Attribution(workspace_id=workspace_id),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        execution_outcome=ExecutionOutcome.SUCCEEDED,
        tokens=TokenBreakdown(),
        usage_origin=UsageOrigin.PROVIDER_REPORTED,
        usage_completeness=UsageCompleteness.COMPLETE,
    )
    base.update(overrides)
    return UsageRecord(**base)


def test_minimal_construction():
    r = _minimal_record()
    assert r.contract_version == 1
    assert r.currency == "USD"
    assert r.pricing_completeness is PricingCompleteness.UNPRICED
    assert r.calculated_cost_microdollars is None


def test_frozen_records_reject_mutation():
    r = _minimal_record()
    with pytest.raises(FrozenInstanceError):
        r.model = "gpt-5"  # type: ignore[misc]


def test_reasoning_is_subset_of_output_not_additive():
    """Invariant #5: reasoning_output_tokens is a breakdown of total_output_tokens."""
    tokens = TokenBreakdown(
        total_output_tokens=100,
        reasoning_output_tokens=30,
    )
    assert tokens.total_output_tokens == 100  # not 130
    assert tokens.reasoning_output_tokens == 30


def test_known_zero_distinct_from_missing():
    """Invariant #4."""
    zero = TokenBreakdown(total_output_tokens=0)
    missing = TokenBreakdown(total_output_tokens=None)
    assert zero.total_output_tokens == 0
    assert missing.total_output_tokens is None
    assert zero != missing


def test_fallback_chain_via_parent_receipt_id():
    first = uuid4()
    second_identity = AttemptIdentity(
        receipt_id=uuid4(),
        request_id=uuid4(),
        attempt_ordinal=1,
        parent_receipt_id=first,
    )
    assert second_identity.attempt_ordinal == 1
    assert second_identity.parent_receipt_id == first


def test_cache_tiers_and_modality_units_default_empty():
    tokens = TokenBreakdown()
    assert tokens.cache_write_tokens_by_tier == {}
    assert tokens.modality_units == {}


def test_microdollar_roundtrip_preserves_cents():
    """1.23 USD roundtrips through integer microdollars without drift."""
    micro = microdollars_from_usd(Decimal("1.23"))
    assert micro == 1_230_000
    assert usd_from_microdollars(micro) == Decimal("1.23")


def test_microdollar_from_float_and_int():
    assert microdollars_from_usd(0) == 0
    assert microdollars_from_usd(1) == 1_000_000
    # Sub-microdollar rounds to nearest even (Decimal default).
    assert microdollars_from_usd(Decimal("0.0000005")) in (0, 1)
