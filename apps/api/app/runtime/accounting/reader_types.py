"""Accounting read-API result types (split from reader.py; re-exported there)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Mapping, Optional

from app.runtime.accounting.contracts import (
    MICRODOLLARS_PER_USD,
    PricingCompleteness,
    UsageCompleteness,
)


class AggregateScope(str, Enum):
    """How to group the aggregate query."""

    WORKSPACE = "workspace"
    DEVELOPER = "developer_user_id"
    AGENT_IDENTITY = "agent_identity_id"
    MODEL = "model"
    PROVIDER = "provider"
    CLIENT_TOOL = "client_tool"
    WORKFLOW_RUN = "workflow_run_id"
    HOOK_SESSION = "hook_session_id"


@dataclass(frozen=True)
class SpendAggregate:
    """One aggregated slice of accounting evidence.

    Every field is a fact derived from ``llm_attempt_receipts`` rows.
    Callers (Lens, dashboards, exports) MUST preserve the completeness
    breakdown when displaying numbers so users can tell "$5.00 reported"
    apart from "$5.00 partially reported, actual may be higher".
    """

    scope: Mapping[str, Optional[str]]
    period_start: datetime
    period_end: datetime

    # Row counts
    receipt_count: int
    request_count: int  # distinct request_ids

    # Money (integer microdollars, per contract)
    total_cost_microdollars: int
    total_reserved_microdollars: int

    # Legacy comparison (Session 6 metrics)
    legacy_cost_microdollars: int

    # Token totals — nullable? No, aggregate treats NULL as 0 for sums.
    # The distinction lives in `completeness_breakdown` below.
    total_input_tokens: int
    total_output_tokens: int
    total_uncached_input_tokens: int
    total_cache_read_tokens: int
    total_reasoning_output_tokens: int

    # Provenance breakdowns
    completeness_breakdown: Mapping[str, int] = field(default_factory=dict)
    pricing_completeness_breakdown: Mapping[str, int] = field(default_factory=dict)
    execution_outcome_breakdown: Mapping[str, int] = field(default_factory=dict)

    @property
    def total_cost_usd(self) -> Decimal:
        """Convenience for display. Ledger arithmetic stays in microdollars."""
        return Decimal(self.total_cost_microdollars) / Decimal(MICRODOLLARS_PER_USD)

    @property
    def has_partial_or_missing(self) -> bool:
        """True if any receipts in this aggregate have incomplete usage.

        Lens should surface a caveat next to any number derived from an
        aggregate where this is True.
        """
        return any(
            key != UsageCompleteness.COMPLETE.value and count > 0
            for key, count in self.completeness_breakdown.items()
        )

    @property
    def has_unpriced_attempts(self) -> bool:
        """True if any attempts could not be priced (unknown model, strict
        rejection). Lens must NOT report ``total_cost_microdollars`` as the
        exact spend when this is True; the true cost is at least the
        reported figure."""
        unpriced = self.pricing_completeness_breakdown.get(
            PricingCompleteness.UNPRICED.value, 0
        )
        return unpriced > 0


@dataclass(frozen=True)
class SessionSpend:
    """Per-session accounting rollup for the Lens Sessions list.

    Post-#2221 PR 1 (consumer wiring): AccountingReader
    ``spend_by_hook_session_ids()`` returns one of these per session so
    Lens's UI can render both the number AND the caveats (partial /
    unpriced) — invariants #4 and #9 preserved end-to-end.
    """

    hook_session_id: uuid.UUID
    receipt_count: int
    request_count: int
    total_cost_microdollars: int
    has_partial_or_missing: bool
    has_unpriced_attempts: bool

    @property
    def total_cost_usd(self) -> Decimal:
        return Decimal(self.total_cost_microdollars) / Decimal(1_000_000)


@dataclass(frozen=True)
class CacheReadSavings:
    """Gross cache-READ savings for one (model, pricing_version) slice.

    Reviewer #6 (#2221 review at 1219d734) narrowed the scope: the
    previous ``CacheSavings`` dataclass mixed one rate pair against an
    aggregate that could span multiple models. It also hardcoded
    ``cache_write_tokens=0`` and ignored its ``cache_write_rate``
    argument, producing an answer that looked authoritative but wasn't.

    What this IS:
      Gross cache-read savings — how much less the cache_read tokens
      cost vs. if the same bytes had been billed at the uncached input
      rate. Only meaningful for one (model, pricing_version) slice.

    What this is NOT:
      - A net "cache saved you $X" figure. Cache writes usually cost
        MORE than uncached input to pay for later reads; that premium
        is a separate arithmetic and lives in
        ``compute_cache_write_premium_for_receipt``.
      - A workspace-wide savings summary. Aggregating across models
        with different rate cards requires per-receipt calculation;
        use ``sum_cache_read_savings_over_receipts``.
    """

    cache_read_tokens: int
    uncached_input_tokens: int
    savings_microdollars: int
    counterfactual_read_cost_microdollars: int


# Kept as an alias for one release so external importers do not break.
# Session 7 removal deletes it.
CacheSavings = CacheReadSavings
