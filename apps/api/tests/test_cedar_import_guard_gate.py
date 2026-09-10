"""Cedar import/export guard gate (#1768 / Option 1 of the design conversation).

The gate helper `_enforce_cedar_gate` composes the same evaluator every other
surface uses AND writes a hash-chained audit receipt for every decision.
These tests patch `evaluate_composed` + `_record_event` and verify:

- BLOCK    → HTTPException(403) + receipt written with decision="blocked"
- APPROVAL → HTTPException(428) + receipt written with decision="approval_pending"
- ALLOW    → returns silently + receipt written with decision="allowed"
- WARN     → returns silently + receipt written with decision="warned"
- No decision (no match) → receipt written with decision="allowed", rule_id=None
- Evaluator raises → fail-open + receipt written with decision="allowed"
- Receipt write failure → gate still enforces (fail-open on the audit side too)

The corresponding conduct-base rules (`cedar-import-audit`, `cedar-export-audit`)
default to `action: audit` — no BLOCK/APPROVAL until an admin overrides.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.routers.cedar_import import _enforce_cedar_gate


VALID_WS = "00000000-0000-0000-0000-0000000000aa"


def _decision(action: PolicyAction) -> PolicyDecision:
    return PolicyDecision(
        action=action,
        source="test",
        reason="test-reason",
        rule_id="cedar-test-rule",
    )


def test_allow_returns_silently_and_writes_receipt():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.ALLOW)), \
         patch("app.routers.cedar_import._record_event") as rec:
        _enforce_cedar_gate(
            db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
            tool_name="cedar_import", payload={"pack_slug": "foo"},
        )
    assert rec.call_count == 1
    kwargs = rec.call_args.kwargs
    assert kwargs["decision"] == "allowed"
    assert kwargs["rule_id"] == "cedar-test-rule"
    assert kwargs["tool_name"] == "cedar_import"
    assert kwargs["source"] == "http"


def test_none_decision_writes_allowed_receipt_with_no_rule():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=None), \
         patch("app.routers.cedar_import._record_event") as rec:
        _enforce_cedar_gate(
            db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )
    assert rec.call_count == 1
    assert rec.call_args.kwargs["decision"] == "allowed"
    assert rec.call_args.kwargs["rule_id"] is None


def test_warn_returns_silently_and_writes_warned_receipt():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.WARN)), \
         patch("app.routers.cedar_import._record_event") as rec:
        _enforce_cedar_gate(
            db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )
    assert rec.call_args.kwargs["decision"] == "warned"


def test_block_raises_403_and_writes_blocked_receipt():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.BLOCK)), \
         patch("app.routers.cedar_import._record_event") as rec:
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
                tool_name="cedar_import", payload={},
            )
    assert exc_info.value.status_code == 403
    assert "cedar-test-rule" in exc_info.value.detail
    assert "test-reason" in exc_info.value.detail
    assert rec.call_args.kwargs["decision"] == "blocked"
    assert rec.call_args.kwargs["rule_id"] == "cedar-test-rule"


def test_approval_raises_428_and_writes_pending_receipt():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.APPROVAL)), \
         patch("app.routers.cedar_import._record_event") as rec:
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
                tool_name="cedar_import", payload={},
            )
    assert exc_info.value.status_code == 428
    assert "cedar-test-rule" in exc_info.value.detail
    assert rec.call_args.kwargs["decision"] == "approval_pending"


def test_evaluator_exception_fails_open_and_still_writes_receipt():
    def _boom(_ctx):
        raise RuntimeError("policy_engine broken")

    with patch("app.routers.cedar_import.evaluate_composed", side_effect=_boom), \
         patch("app.routers.cedar_import._record_event") as rec:
        _enforce_cedar_gate(
            db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
            tool_name="cedar_import", payload={},
        )
    assert rec.call_args.kwargs["decision"] == "allowed"


def test_receipt_write_failure_does_not_break_enforcement():
    """If _record_event throws, the gate still enforces (BLOCK still 403)."""
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.BLOCK)), \
         patch("app.routers.cedar_import._record_event", side_effect=RuntimeError("db down")):
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
                tool_name="cedar_import", payload={},
            )
    assert exc_info.value.status_code == 403


def test_gate_reused_for_export_intent():
    with patch("app.routers.cedar_import.evaluate_composed", return_value=_decision(PolicyAction.BLOCK)), \
         patch("app.routers.cedar_import._record_event") as rec:
        with pytest.raises(HTTPException) as exc_info:
            _enforce_cedar_gate(
                db=None, workspace_id=VALID_WS, clerk_user_id="u-1",
                tool_name="cedar_export", payload={"pack_slug": "conduct-hipaa"},
            )
    assert exc_info.value.status_code == 403
    assert rec.call_args.kwargs["tool_name"] == "cedar_export"


def test_ctx_shape_passed_to_evaluator():
    """PolicyContext gets the intent as body + surface="http" in extras."""
    captured = {}

    def _capture(ctx):
        captured["ctx"] = ctx
        return _decision(PolicyAction.ALLOW)

    with patch("app.routers.cedar_import.evaluate_composed", side_effect=_capture), \
         patch("app.routers.cedar_import._record_event"):
        _enforce_cedar_gate(
            db=None,
            workspace_id=VALID_WS,
            clerk_user_id="clerk-abc",
            tool_name="cedar_import",
            payload={"pack_slug": "foo", "rule_count": 12},
        )

    ctx = captured["ctx"]
    assert ctx.workspace_id == VALID_WS
    assert ctx.clerk_user_id == "clerk-abc"
    assert ctx.provider == "conduct"
    assert ctx.model == "cedar_import"
    assert ctx.body == {
        "tool_name": "cedar_import",
        "arguments": {"pack_slug": "foo", "rule_count": 12},
    }
    assert ctx.extras.get("surface") == "http"
    assert ctx.extras.get("tool_name") == "cedar_import"
