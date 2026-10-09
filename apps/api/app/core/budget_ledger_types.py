"""Budget ledger decision enum, unit constants and Reservation record.

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BudgetDecision(Enum):
    ACCEPTED = "accepted"
    EXCEEDED = "exceeded"
    REDIS_DOWN = "redis_down"
    NOT_READY = "not_ready"
    DISABLED = "disabled"


# R9 (reviewer P1): microdollar unit constants. Exposed for tests that
# want to construct Reservation objects directly.
_MICROS_PER_CENT = 10_000
_MICROS_PER_USD = 1_000_000


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    workspace_id: str
    ai_tool: str
    estimated_cents: int
    period_key: str
    # Fix 1 (P1 #1): scope fields so release/commit can reconstruct the
    # exact Redis key reserve() wrote against.
    clerk_user_id: str | None = None
    agent_identity_id: str | None = None
    # R9 (reviewer P1): microdollar precision for the durable log.
    # None = legacy cents-mode reservation. Non-None = precise value
    # scaled by _MICROS_PER_CENT.
    estimated_micros: int | None = None
