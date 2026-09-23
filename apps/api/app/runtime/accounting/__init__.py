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
]
