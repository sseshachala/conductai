"""Typed contracts for unified LLM accounting (issue #2209).

Storage-agnostic. No behavior. Session 1 deliverable.

Contract version bumps require a documented migration path — historical rows
are pinned to the version that wrote them (invariant: no silent recompute).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Optional
from uuid import UUID

CONTRACT_VERSION = 1

# 1 USD = 1_000_000 microdollars. Storage + arithmetic use int microdollars;
# Decimal / display rounding happens at ledger boundaries only.
MICRODOLLARS_PER_USD = 1_000_000


class ExecutionOutcome(str, Enum):
    """Terminal state of one paid upstream attempt.

    REJECTED_PREFLIGHT means the request was denied before dispatch — no
    upstream call, no charge. DISCONNECTED means the client dropped; provider
    may still have charged us. FAILED means we dispatched and got an error but
    may still owe the provider.
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REJECTED_PREFLIGHT = "rejected_preflight"
    DISCONNECTED = "disconnected"
    RECONCILED_LATE = "reconciled_late"


class UsageOrigin(str, Enum):
    """Where the token counts came from."""

    PROVIDER_REPORTED = "provider_reported"
    NORMALIZED_STREAM = "normalized_stream"
    ESTIMATED = "estimated"
    RECONCILED = "reconciled"
    MISSING = "missing"


class UsageCompleteness(str, Enum):
    """Distinguishes complete vs partial vs pending vs unavailable.

    Zero is not the same as missing. A legitimate zero-output response is
    COMPLETE with output=0; a stream cut mid-flight is PARTIAL; a provider
    that never reported usage is UNAVAILABLE; a call waiting for
    reconciliation is PENDING.
    """

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    PENDING = "pending"


class PricingCompleteness(str, Enum):
    """Pricing availability, independent of usage completeness."""

    PRICED = "priced"
    UNPRICED = "unpriced"
    INCOMPLETE = "incomplete"
    OVERRIDE_APPLIED = "override_applied"


@dataclass(frozen=True)
class AttemptIdentity:
    """Uniquely identifies one paid upstream attempt.

    A single HTTP request can produce N attempts (retries, fallbacks). Each
    attempt has its own receipt_id; they share request_id and are ordered by
    attempt_ordinal (0-indexed). Fallback chains link via parent_receipt_id.
    """

    receipt_id: UUID
    request_id: UUID
    attempt_ordinal: int
    parent_receipt_id: Optional[UUID] = None
    workflow_run_id: Optional[UUID] = None
    workflow_step_id: Optional[UUID] = None


@dataclass(frozen=True)
class Attribution:
    """Trusted execution context. Never client-supplied labels.

    developer_user_id may be None for unowned service agents; do not invent
    a developer for them (invariant #2).
    """

    workspace_id: UUID
    developer_user_id: Optional[UUID] = None
    agent_identity_id: Optional[UUID] = None
    source: Optional[str] = None
    client_tool: Optional[str] = None
    transport: Optional[str] = None


@dataclass(frozen=True)
class TokenBreakdown:
    """Nullable-by-design token counts with documented inclusion semantics.

    - total_input_tokens INCLUDES cache_read_tokens.
    - total_output_tokens INCLUDES reasoning_output_tokens (invariant #5:
      reasoning is a breakdown, not an additive charge).
    - cache_write_tokens_by_tier keyed by tier identifier
      (e.g. "ephemeral_5m", "ephemeral_1h" for Anthropic).
    - modality_units for non-token billable units (e.g. "audio_seconds").

    None means "not reported". 0 means "reported as zero" — the two are
    distinct and must remain so through storage / API / UI.
    """

    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    uncached_input_tokens: Optional[int] = None
    cache_read_tokens: Optional[int] = None
    cache_write_tokens_by_tier: Mapping[str, int] = field(default_factory=dict)
    reasoning_output_tokens: Optional[int] = None
    modality_units: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class UsageRecord:
    """One paid upstream attempt = one UsageRecord.

    Versioned so callers written against contract v1 continue to work after
    the schema evolves. Historical rows are pinned to the version that wrote
    them; readers must dispatch on contract_version.
    """

    contract_version: int
    identity: AttemptIdentity
    attribution: Attribution

    provider: str
    model: str  # actual billable model identity (Azure deployment resolved)
    operation: str  # messages.create, chat.completions, responses.create, ...
    execution_outcome: ExecutionOutcome

    tokens: TokenBreakdown
    usage_origin: UsageOrigin
    usage_completeness: UsageCompleteness

    model_alias: Optional[str] = None
    estimated_input_tokens: Optional[int] = None
    reserved_microdollars: Optional[int] = None
    calculated_cost_microdollars: Optional[int] = None
    currency: str = "USD"
    pricing_version: Optional[str] = None
    pricing_completeness: PricingCompleteness = PricingCompleteness.UNPRICED

    normalizer_version: Optional[str] = None
    calculation_provenance: Mapping[str, Any] = field(default_factory=dict)

    started_at: Optional[datetime] = None
    finalized_at: Optional[datetime] = None


def microdollars_from_usd(usd: Decimal | float | int) -> int:
    """Convert a USD amount to integer microdollars.

    Round-half-even at the microdollar boundary. All arithmetic thereafter is
    integer; conversion to display Decimal happens once at ledger boundaries.
    """
    return int((Decimal(str(usd)) * MICRODOLLARS_PER_USD).to_integral_value())


def usd_from_microdollars(microdollars: int) -> Decimal:
    """Convert integer microdollars back to a Decimal USD value."""
    return Decimal(microdollars) / Decimal(MICRODOLLARS_PER_USD)
