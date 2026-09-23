"""Unified accounting engine for LLM usage and cost.

See docs/design/accounting/README.md and issue #2209 for scope.

Session 1: typed contracts only. No behavior change.
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
]
