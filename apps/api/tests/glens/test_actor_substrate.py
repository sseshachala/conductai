"""Actor substrate parity + first-tool smoke (#1297).

Two layers:
  1. ActionRegistry — decide_approval registers, exposes propose/execute.
  2. require_confirmation — propose-only path via stubbed DB writes a row.

End-to-end confirm+dispatch is exercised by a live-DB smoke in a follow-up
integration suite; the propose path here proves the substrate wiring.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.modules.glens.actor import default_action_registry, ActionCtx, ProposeResult
from app.modules.glens.actor.helpers import require_confirmation
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


# ── ActionRegistry parity ────────────────────────────────────────────────────

def test_decide_approval_actionspec_registered():
    spec = default_action_registry.get("decide_approval")
    assert spec is not None
    assert spec.guard_permission == "platform.approvals.decide"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_decide_approval_tooldef_registered():
    """The paired ToolDef fans out to Lens chat + MCP surfaces via
    default_registry."""
    tool = default_registry.get("decide_approval")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


# ── Propose-path validation ──────────────────────────────────────────────────

def _ctx(**over):
    from unittest.mock import MagicMock
    base = dict(
        db=MagicMock(),
        workspace_id="00000000-0000-0000-0000-000000000000",
        clerk_user_id="user_abc",
        user_email="user@example.com",
        session_id=None,
        agent_identity_id=None,
        surface="lens",
    )
    base.update(over)
    return ActionCtx(**base)


def test_propose_rejects_missing_id():
    spec = default_action_registry.get("decide_approval")
    out = spec.propose(_ctx(), {"decision": "approved"})
    assert out.rejected
    assert "approval_request_id" in (out.reason or "")


def test_propose_rejects_bad_decision():
    spec = default_action_registry.get("decide_approval")
    out = spec.propose(_ctx(), {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "maybe",
    })
    assert out.rejected


def test_propose_rejects_reject_without_reason():
    spec = default_action_registry.get("decide_approval")
    out = spec.propose(_ctx(), {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "rejected",
    })
    assert out.rejected
    assert "reason" in (out.reason or "").lower()


def test_propose_rejects_bad_uuid():
    spec = default_action_registry.get("decide_approval")
    out = spec.propose(_ctx(), {
        "approval_request_id": "not-a-uuid",
        "decision": "approved",
    })
    assert out.rejected


def test_propose_rejects_missing_approval_row():
    """DB returns no row → propose rejects with 'not found'."""
    spec = default_action_registry.get("decide_approval")
    ctx = _ctx()
    ctx.db.query.return_value.filter.return_value.first.return_value = None
    out = spec.propose(ctx, {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "approved",
    })
    assert out.rejected
    assert "not found" in (out.reason or "").lower()


def test_propose_rejects_already_decided():
    spec = default_action_registry.get("decide_approval")
    ctx = _ctx()
    row = SimpleNamespace(
        id="fake", status="approved",
        rule_message="Run 'x'", tool_name="run_workflow", rule_id="lens.actor.confirm.run_workflow",
        requester_email="req@x", requester_user_id="req_u",
        source_run_id=None, approval_type="any_authorized", approval_group=None,
    )
    ctx.db.query.return_value.filter.return_value.first.return_value = row
    out = spec.propose(ctx, {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "approved",
    })
    assert out.rejected
    assert "already approved" in (out.reason or "").lower()


def test_propose_success_shape():
    spec = default_action_registry.get("decide_approval")
    ctx = _ctx()
    row = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        status="pending",
        rule_message="Run 'nightly'", tool_name="run_workflow",
        rule_id="lens.actor.confirm.run_workflow",
        requester_email="alice@example.com", requester_user_id="user_alice",
        source_run_id=None, approval_type="any_authorized", approval_group=None,
    )
    ctx.db.query.return_value.filter.return_value.first.return_value = row
    out: ProposeResult = spec.propose(ctx, {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "approved",
    })
    assert not out.rejected
    assert "Approve" in out.summary
    assert "alice" in out.summary
    assert out.resolved_input["decision"] == "approved"


def test_propose_success_reject_carries_reason_into_summary():
    spec = default_action_registry.get("decide_approval")
    ctx = _ctx()
    row = SimpleNamespace(
        id="11111111-1111-1111-1111-111111111111",
        status="pending",
        rule_message="Run 'prod deploy'", tool_name="run_workflow",
        rule_id="lens.actor.confirm.run_workflow",
        requester_email="bob@example.com", requester_user_id="user_bob",
        source_run_id=None, approval_type="any_authorized", approval_group=None,
    )
    ctx.db.query.return_value.filter.return_value.first.return_value = row
    out = spec.propose(ctx, {
        "approval_request_id": "11111111-1111-1111-1111-111111111111",
        "decision": "rejected",
        "reason": "not tonight",
    })
    assert not out.rejected
    assert "Reject" in out.summary
    assert "not tonight" in out.summary
