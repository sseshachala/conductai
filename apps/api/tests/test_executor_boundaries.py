from __future__ import annotations

from app.runtime.executor import _classify_failure


def test_turn_budget_boundary_maps_to_deterministic_stop_reason():
    exc = RuntimeError(
        "Turn budget exhausted: agent did not reach end_turn after 20 turns (100 input / 80 output tokens, $0.1200)"
    )
    summary = _classify_failure(exc)

    assert summary["code"] == "RETRY_BUDGET_EXHAUSTED"
    assert summary["stop_reason"] == "max_turns_reached"
    assert "increase the run turn budget" in summary["next_action"]


def test_cost_budget_boundary_maps_to_deterministic_stop_reason():
    exc = RuntimeError(
        "Cost budget exhausted: agent reached $5.5000 with cap $5.0000 after 7 turns"
    )
    summary = _classify_failure(exc)

    assert summary["code"] == "COST_BUDGET_EXHAUSTED"
    assert summary["stop_reason"] == "max_cost_reached"
    assert "raise the cost cap" in summary["next_action"]
