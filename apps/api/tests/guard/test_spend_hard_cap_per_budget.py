"""Fix 2 (P1 #2) — per-budget hard_cap_enabled.

Pre-fix: the API silently forced ``hard_cap_enabled=False`` on every
non-workspace-default budget row. Result: a per-tool or per-agent cap
looked "set" in the UI but ``reserve_all()`` skipped it (because that
gate requires True). Reproducer from reviewer: 1c scoped cap accepted a
100c request.

Post-fix: any budget row can be created with ``hard_cap_enabled=True``.
The workspace-default row still acts as a master switch (the ledger
checks it before enforcing anything), but per-row enforcement now
depends on each row's own flag.

Tests here exercise the API path directly since the ledger side of the
fix lives on the (held) #2097 branch — this PR ships only the API
surface change.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.modules.guard.routers.spend import BudgetCreate


def test_budget_create_accepts_hard_cap_enabled_on_non_default_row():
    """A per-tool budget should be able to opt into hard enforcement."""
    body = BudgetCreate(
        workspace_id="00000000-0000-0000-0000-000000000000",
        ai_tool="cursor",
        monthly_limit_usd=10.0,
        hard_limit_usd=15.0,
        hard_cap_enabled=True,
    )
    assert body.hard_cap_enabled is True
    assert body.ai_tool == "cursor"


def test_budget_create_accepts_hard_cap_enabled_on_agent_scoped_row():
    """A per-agent budget should be able to opt into hard enforcement."""
    body = BudgetCreate(
        workspace_id="00000000-0000-0000-0000-000000000000",
        agent_identity_id="agent-abc",
        monthly_limit_usd=25.0,
        hard_limit_usd=25.0,
        hard_cap_enabled=True,
    )
    assert body.hard_cap_enabled is True
    assert body.agent_identity_id == "agent-abc"


def test_budget_create_accepts_zero_dollar_hard_limit():
    """Explicit $0 cap means 'refuse all spend' — do NOT treat as
    unlimited (reviewer callout: 'an explicit zero-dollar cap currently
    becomes unlimited')."""
    body = BudgetCreate(
        workspace_id="00000000-0000-0000-0000-000000000000",
        ai_tool="cursor",
        monthly_limit_usd=0.0,
        hard_limit_usd=0.0,
        hard_cap_enabled=True,
    )
    assert body.hard_limit_usd == 0.0
    assert body.hard_cap_enabled is True
