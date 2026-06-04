from __future__ import annotations

from app.runtime.run_contract import enrich_run_state_contract


def test_enrich_run_state_contract_stamps_unified_envelope_without_mutating_input():
    initial = {"_trigger": {"event_type": "manual"}, "foo": "bar"}

    enriched = enrich_run_state_contract(
        initial,
        source="manual:create_run",
        trigger_provider="manual",
        workflow_id="wf_123",
        workspace_id="ws_123",
        max_turns=20,
    )

    assert initial == {"_trigger": {"event_type": "manual"}, "foo": "bar"}
    assert enriched["__max_turns"] == 20
    assert enriched["__max_cost_usd"] == 5.0
    assert enriched["__run_explainability"]["source"] == "manual:create_run"
    assert enriched["__run_explainability"]["trigger_provider"] == "manual"
    assert enriched["__run_explainability"]["budget"]["max_turns"] == 20
    assert enriched["__governance"]["policy_surface"] == "unified"
    assert enriched["__governance"]["provider"] == "manual"


def test_enrich_run_state_contract_applies_floor_for_turns_and_cost():
    enriched = enrich_run_state_contract(
        {},
        source="github:issues",
        trigger_provider="github",
        workflow_id="wf_abc",
        workspace_id="ws_abc",
        max_turns=0,
        max_cost_usd=0.0,
    )

    assert enriched["__max_turns"] == 1
    assert enriched["__max_cost_usd"] == 0.01
    assert enriched["__run_explainability"]["budget"]["max_turns"] == 1
    assert enriched["__run_explainability"]["budget"]["max_cost_usd"] == 0.01
    assert enriched["__governance"]["provider"] == "github"
