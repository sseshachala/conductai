"""#1302 — actor ActionSpec + ToolDef parity for update_budget.

Propose-path only; live-DB confirm+dispatch is covered by the actor
substrate integration suite. Same shape as tests/glens/test_actor_run_workflow.py.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_WS = "00000000-0000-0000-0000-000000000000"
_BUD = "11111111-1111-1111-1111-111111111111"


def _ctx(**over):
    base = dict(
        db=MagicMock(),
        workspace_id=_WS,
        clerk_user_id="user_abc",
        user_email="user@example.com",
        session_id=None,
        agent_identity_id=None,
        surface="lens",
    )
    base.update(over)
    return ActionCtx(**base)


def _fake_budget(clerk_user_id=None, monthly=500.0):
    return SimpleNamespace(
        id=uuid.UUID(_BUD),
        workspace_id=uuid.UUID(_WS),
        clerk_user_id=clerk_user_id,
        monthly_limit_usd=monthly,
    )


def _mock_db_returning(budget):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = budget
    return db


def test_update_budget_actionspec_registered():
    spec = default_action_registry.get("update_budget")
    assert spec is not None
    assert spec.guard_permission == "guard.spend.budgets.edit"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_update_budget_tooldef_registered():
    tool = default_registry.get("update_budget")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_propose_rejects_empty_id():
    spec = default_action_registry.get("update_budget")
    out = spec.propose(_ctx(), {"monthly_limit_usd": 1000})
    assert out.rejected
    assert "budget_id required" in (out.reason or "")


def test_propose_rejects_invalid_uuid():
    spec = default_action_registry.get("update_budget")
    out = spec.propose(_ctx(), {"budget_id": "not-a-uuid", "monthly_limit_usd": 1000})
    assert out.rejected
    assert "not a valid UUID" in (out.reason or "")


def test_propose_rejects_non_numeric_limit():
    spec = default_action_registry.get("update_budget")
    out = spec.propose(_ctx(), {"budget_id": _BUD, "monthly_limit_usd": "abc"})
    assert out.rejected
    assert "must be a number" in (out.reason or "")


def test_propose_rejects_negative_limit():
    spec = default_action_registry.get("update_budget")
    out = spec.propose(_ctx(), {"budget_id": _BUD, "monthly_limit_usd": -1})
    assert out.rejected
    assert "cannot be negative" in (out.reason or "")


def test_propose_rejects_missing_budget():
    spec = default_action_registry.get("update_budget")
    db = _mock_db_returning(None)
    out = spec.propose(_ctx(db=db), {"budget_id": _BUD, "monthly_limit_usd": 1000})
    assert out.rejected
    assert "No budget matches id" in (out.reason or "")


def test_propose_success_workspace_wide_shape():
    spec = default_action_registry.get("update_budget")
    db = _mock_db_returning(_fake_budget(clerk_user_id=None, monthly=500))
    out = spec.propose(_ctx(db=db), {"budget_id": _BUD, "monthly_limit_usd": 1000})
    assert not out.rejected
    assert "workspace-wide" in out.summary
    assert "$500.00 → $1000.00" in out.summary
    assert out.resolved_input == {
        "budget_id": _BUD,
        "monthly_limit_usd": 1000.0,
        "old_limit_usd": 500.0,
        "clerk_user_id": None,
    }


def test_propose_success_per_user_shape():
    spec = default_action_registry.get("update_budget")
    db = _mock_db_returning(_fake_budget(clerk_user_id="user_xyz", monthly=200))
    out = spec.propose(_ctx(db=db), {"budget_id": _BUD, "monthly_limit_usd": 300})
    assert not out.rejected
    assert "user_xyz" in out.summary
    assert out.resolved_input["clerk_user_id"] == "user_xyz"
