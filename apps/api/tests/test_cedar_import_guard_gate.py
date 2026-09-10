"""Cedar import/export guard gate (#1764 / Option 1 of the design conversation).

The gate helper `_enforce_cedar_gate` composes the same evaluator every other
surface uses. These tests patch `evaluate_composed` and verify:

- BLOCK    → HTTPException(403) with rule_id + reason in detail
- APPROVAL → HTTPException(428) with rule_id + reason in detail
- ALLOW / WARN / no decision → returns silently (allows request to proceed)
- Evaluator raises → fail-open (returns silently, matches proxy/lens)

The corresponding conduct-base rules (`cedar-import-audit`, `cedar-export-audit`)
default to `action: audit` — no BLOCK/APPROVAL until an admin overrides.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.routers.cedar_import import _enforce_cedar_gate


def _decision(action: PolicyAction) -> PolicyDecision:
    return PolicyDecision(
        action=action,
        source="test",
        reason="test-reason",
        rule_id="cedar-test-rule",
    )


def test_allow_returns_silently():
    with patch(
        "app.routers.cedar_import.evaluate_composed",
        return_value=_decision(PolicyAction.ALLOW),
    ):
        _enforce_cedar_gate(
            db=None, workspace_id="ws-1", clerk_user_id="u-1",
            tool_name="cedar_import", payload={"pack_slug": "foo"},
        )


def test_none_decision_returns_silently():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=None):
        _enforce_cedar_gate(
            db=None, workspace_id="ws-1", clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )


def test_warn_returns_silently():
    with patch(
        "app.routers.cedar_import.evaluate_composed",
        return_value=_decision(PolicyAction.WARN),
    ):
        _enforce_cedar_gate(
            db=None, workspace_id="ws-1", clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )


def test_block_raises_403_with_rule_and_reason():
    with patch(
        "app.routers.cedar_import.evaluate_composed",
        return_value=_decision(PolicyAction.BLOCK),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id="ws-1", clerk_user_id="u-1",
                tool_name="cedar_import", payload={},
            )
    assert exc_info.value.status_code == 403
    assert "cedar-test-rule" in exc_info.value.detail
    assert "test-reason" in exc_info.value.detail


def test_approval_raises_428_with_rule_and_reason():
    with patch(
        "app.routers.cedar_import.evaluate_composed",
        return_value=_decision(PolicyAction.APPROVAL),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id="ws-1", clerk_user_id="u-1",
                tool_name="cedar_import", payload={},
            )
    assert exc_info.value.status_code == 428
    assert "cedar-test-rule" in exc_info.value.detail


def test_evaluator_exception_fails_open():
    """Matches proxy/lens behaviour: eval failure logs a warning + returns."""
    def _boom(_ctx):
        raise RuntimeError("policy_engine broken")

    with patch("app.routers.cedar_import.evaluate_composed", side_effect=_boom):
        _enforce_cedar_gate(
            db=None, workspace_id="ws-1", clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )


def test_gate_reused_for_export_intent():
    """Same helper handles cedar_export intent — tool_name is the discriminator."""
    with patch(
        "app.routers.cedar_import.evaluate_composed",
        return_value=_decision(PolicyAction.BLOCK),
    ):
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id="ws-1", clerk_user_id="u-1",
                tool_name="cedar_export", payload={"pack_slug": "conduct-hipaa"},
            )
    assert exc_info.value.status_code == 403


def test_ctx_shape_passed_to_evaluator():
    """Confirm the PolicyContext receives the intent as body + surface="http" in extras."""
    captured = {}

    def _capture(ctx):
        captured["ctx"] = ctx
        return _decision(PolicyAction.ALLOW)

    with patch("app.routers.cedar_import.evaluate_composed", side_effect=_capture):
        _enforce_cedar_gate(
            db=None,
            workspace_id="ws-xyz",
            clerk_user_id="clerk-abc",
            tool_name="cedar_import",
            payload={"pack_slug": "foo", "rule_count": 12},
        )

    ctx = captured["ctx"]
    assert ctx.workspace_id == "ws-xyz"
    assert ctx.clerk_user_id == "clerk-abc"
    assert ctx.provider == "conduct"
    assert ctx.model == "cedar_import"
    assert ctx.body == {
        "tool_name": "cedar_import",
        "arguments": {"pack_slug": "foo", "rule_count": 12},
    }
    assert ctx.extras.get("surface") == "http"
    assert ctx.extras.get("tool_name") == "cedar_import"
