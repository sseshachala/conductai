from __future__ import annotations

from app.runtime.executor import _classify_failure


def test_classify_failure_emits_actionable_contract_fields():
    summary = _classify_failure(PermissionError("egress denied"), block_id="brain_1")

    assert summary["code"] == "EGRESS_POLICY_BLOCKED"
    assert summary["category"] == "governance"
    assert summary["stop_reason"] == "policy_block"
    assert summary["next_action"]
    assert summary["block_id"] == "brain_1"


def test_classify_failure_maps_needs_clarification_to_input_contract():
    summary = _classify_failure(ValueError("NEEDS_CLARIFICATION: missing repo context"))

    assert summary["code"] == "INSUFFICIENT_INPUT_CONTEXT"
    assert summary["category"] == "input_contract"
    assert summary["stop_reason"] == "missing_context"
    assert "Provide clearer trigger context" in summary["next_action"]


# ── Guard block hints — issue #1003 ───────────────────────────────────────────

def test_classify_failure_guard_block_non_overridable_hint():
    """non_overridable rule → hint says 'cannot be disabled', not 'Disable Guard'."""
    exc = RuntimeError("[ConductGuard] Blocked by policy 'no-path-traversal': Path traversal blocked.")
    state = {
        "__governance": {
            "blocked": True,
            "rule_id": "no-path-traversal",
            "non_overridable": True,
            "matched_snippet": "/etc/passwd in evidence",
        }
    }
    summary = _classify_failure(exc, "file_findings", state)
    assert summary["code"] == "GUARD_POLICY_BLOCKED"
    assert "cannot be disabled" in summary["next_action"]
    assert "/etc/passwd in evidence" in summary["next_action"]
    # The misleading "Disable Guard for this workflow" text must be gone
    assert "Disable Guard for this workflow" not in summary["next_action"]


def test_classify_failure_guard_block_overridable_shows_snippet():
    """Overridable rule keeps the default 'Disable Guard' hint but includes snippet."""
    exc = RuntimeError("[ConductGuard] Blocked by policy 'custom-rule': test")
    state = {
        "__governance": {
            "blocked": True,
            "rule_id": "custom-rule",
            "non_overridable": False,
            "matched_snippet": "some pattern hit",
        }
    }
    summary = _classify_failure(exc, "x", state)
    assert "Disable Guard for this workflow" in summary["next_action"]
    assert "some pattern hit" in summary["next_action"]


def test_classify_failure_guard_block_no_state_backwards_compat():
    """Existing call sites without state still get a valid Guard classification."""
    exc = RuntimeError("[ConductGuard] Blocked by policy 'rule-x': test")
    summary = _classify_failure(exc, "x")
    assert summary["code"] == "GUARD_POLICY_BLOCKED"
    assert "Guard rule 'rule-x' blocked this step" in summary["next_action"]
    # Falls back to the generic hint when we don't know if the rule is non_overridable
    assert "Disable Guard" in summary["next_action"]
