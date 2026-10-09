"""Budget ledger period helpers, Redis key builders and misc helpers.

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone


# ── Period helpers ──────────────────────────────────────────────────

def monthly_period_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _period_start(period_key: str) -> datetime:
    year, month = period_key.split("-")
    return datetime(int(year), int(month), 1, tzinfo=timezone.utc)


def _seconds_until_next_period(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int((end - now).total_seconds()) + 3600  # 1h slack


def _scope_slug(user: str | None, agent: str | None, tool: str | None) -> str:
    """Canonical Redis key segment for a budget scope tuple.

    Fix 1 (P1 #1): keys must distinguish
    (user=None, agent=None, tool=None) from (user=None, agent=X, tool=None)
    from (user=Y, agent=None, tool=None). Uses '_' as the None sigil so
    distinct scope tuples never collide on the same Redis counter.
    """
    return f"{user or '_'}:{agent or '_'}:{tool or '_all'}"


def _reserved_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:reserved"


def _committed_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:committed"


def _res_hash_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:res"


# R11 fix (reviewer P1): known server-stamped transport identifiers. A
# budget row keyed on one of these caps aggregate spend routed through
# that surface regardless of client_tool. The reconciler must filter
# audit events by ``source == transport`` (not ai_tool) so cursor +
# claude-code + all other client tools flowing through the gateway
# count against the gateway cap.
#
# Source of truth: config/transports.json. Hardcoded here to avoid an
# import cycle on ledger init.
_TRANSPORT_IDS = frozenset({"gateway", "mcp", "workflow", "runtime"})


def _is_transport(ai_tool: str | None) -> bool:
    """True when ai_tool names a server-stamped transport surface."""
    return ai_tool in _TRANSPORT_IDS


def _ready_key(ws, user, agent, tool, period):
    """Set after reconciler completes; presence means the counters
    reflect the durable log."""
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:ready"


def _scope_keys(
    ws: str,
    user: str | None,
    agent: str | None,
    tool: str | None,
    period: str,
) -> dict[str, str]:
    """Return every Redis key for a budget scope tuple in one shot.

    Post Fix 1 (P1 #1) every ledger operation that touches Redis needs
    the same four keys keyed by the same 5-tuple. This helper collapses
    the four sibling calls into one dict lookup so a caller cannot
    accidentally pass different scopes to reserved vs committed vs
    res_hash vs ready — one source of truth, byte-identical output.
    """
    prefix = f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}"
    return {
        "reserved":  f"{prefix}:reserved",
        "committed": f"{prefix}:committed",
        "res_hash":  f"{prefix}:res",
        "ready":     f"{prefix}:ready",
    }


# ── Helpers ──────────────────────────────────────────────────────────

def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError, TypeError):
        return False
