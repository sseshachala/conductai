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
