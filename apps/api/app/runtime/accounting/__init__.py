"""Unified accounting engine for LLM usage and cost.

See docs/design/accounting/README.md and issue #2209 for scope.

Sessions delivered so far:
- Session 1: typed contracts (contracts.py). No behavior change.
- Session 2: shared pricing service + unified estimator, behind compat wrappers.
- Session 3: protocol-family normalizers (Anthropic + OpenAI + LiteLLM).
"""

from app.runtime.accounting.contracts import (
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
from app.runtime.accounting.estimator import (
    ALL_SHAPES,
    ESTIMATOR_VERSION,
    InputShape,
    TokensEstimate,
    estimate_tokens,
)
from app.runtime.accounting.normalizers import (
    NORMALIZER_VERSION,
    AnthropicMessagesNormalizer,
    LiteLLMNormalizer,
    NormalizedUsage,
    OpenAIChatNormalizer,
    OpenAIResponsesNormalizer,
    ProviderFamily,
    SSEEvent,
    SSEParser,
    get_normalizer,
    normalize_json,
    normalize_sse,
)
from app.runtime.accounting.pricing import (
    PriceResult,
    PricingService,
    RateCard,
    default_pricing_service,
    reset_default_pricing_service,
)
from app.runtime.accounting.metrics import (
    DeltaBucket,
    ShadowDeltaReport,
    compute_deltas_from_rows,
    compute_shadow_delta_report,
)
from app.runtime.accounting.reconciler import (
    ReconciliationResult,
    reconcile_missing_receipts,
)
from app.runtime.accounting.flight_recorder_links import (
    flight_recorder_attempt_url,
    flight_recorder_enabled,
    flight_recorder_request_url,
)
from app.runtime.accounting.reader import (
    AccountingReader,
    AggregateScope,
    CacheReadSavings,
    CacheSavings,
    SessionSpend,
    SpendAggregate,
    aggregate_from_rows,
    compute_cache_read_savings,
    compute_cache_read_savings_for_receipt,
    compute_cache_savings,
)

__all__ = [
    "CONTRACT_VERSION",
    "AttemptIdentity",
    "Attribution",
    "ExecutionOutcome",
    "PricingCompleteness",
    "TokenBreakdown",
    "UsageCompleteness",
    "UsageOrigin",
    "UsageRecord",
    "microdollars_from_usd",
    "usd_from_microdollars",
    "ALL_SHAPES",
    "ESTIMATOR_VERSION",
    "InputShape",
    "TokensEstimate",
    "estimate_tokens",
    "PriceResult",
    "PricingService",
    "RateCard",
    "default_pricing_service",
    "reset_default_pricing_service",
    "NORMALIZER_VERSION",
    "AnthropicMessagesNormalizer",
    "LiteLLMNormalizer",
    "NormalizedUsage",
    "OpenAIChatNormalizer",
    "OpenAIResponsesNormalizer",
    "ProviderFamily",
    "SSEEvent",
    "SSEParser",
    "get_normalizer",
    "normalize_json",
    "normalize_sse",
    "AccountingReader",
    "AggregateScope",
    "CacheReadSavings",
    "CacheSavings",
    "SessionSpend",
    "SpendAggregate",
    "aggregate_from_rows",
    "compute_cache_read_savings",
    "compute_cache_read_savings_for_receipt",
    "compute_cache_savings",
    "DeltaBucket",
    "ShadowDeltaReport",
    "compute_deltas_from_rows",
    "compute_shadow_delta_report",
    "ReconciliationResult",
    "reconcile_missing_receipts",
    "flight_recorder_attempt_url",
    "flight_recorder_enabled",
    "flight_recorder_request_url",
]
