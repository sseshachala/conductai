from __future__ import annotations

import pytest

from app.runtime.input_contract import InputContractError, validate_run_start_inputs


def test_rejects_empty_initial_state():
    with pytest.raises(InputContractError):
        validate_run_start_inputs({})


def test_accepts_trigger_shape_and_sets_contract_metadata():
    state = {"_trigger": {"event_type": "manual", "action": "start"}}
    out = validate_run_start_inputs(state)

    assert out["__input_contract"]["status"] == "validated"
    assert out["__input_contract"]["shape"] == "trigger"


def test_rejects_trigger_without_core_signal_fields():
    with pytest.raises(InputContractError):
        validate_run_start_inputs({"_trigger": {"foo": "bar"}})


def test_accepts_github_shape_with_required_fields():
    state = {
        "github_trigger": {"event_type": "github_issue_labeled"},
        "github_issue": {
            "issue_number": 42,
            "title": "Fix build",
            "repo_full_name": "acme/repo",
        },
    }
    out = validate_run_start_inputs(state)

    assert out["__input_contract"]["shape"] == "github"


def test_rejects_github_shape_missing_required_fields():
    state = {
        "github_trigger": {"event_type": "github_issue_labeled"},
        "github_issue": {
            "issue_number": 42,
            "title": "Fix build",
        },
    }
    with pytest.raises(InputContractError):
        validate_run_start_inputs(state)
