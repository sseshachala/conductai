from __future__ import annotations

from copy import deepcopy
from typing import Any


class InputContractError(ValueError):
    """Raised when run-start inputs do not meet the explicit contract."""


def _is_non_empty_dict(value: Any) -> bool:
    return isinstance(value, dict) and bool(value)


def _validate_trigger_shape(trigger: dict[str, Any]) -> None:
    has_core_signal = any(
        key in trigger
        for key in (
            "event_type",
            "action",
            "issue",
            "pull_request",
            "repository",
            "ref",
        )
    )
    if not has_core_signal:
        raise InputContractError(
            "`_trigger` is present but missing required signal fields "
            "(expected one of: event_type, action, issue, pull_request, repository, ref)"
        )


def _validate_github_shape(state: dict[str, Any]) -> None:
    github_trigger = state.get("github_trigger")
    github_issue = state.get("github_issue")
    if not _is_non_empty_dict(github_trigger) or not _is_non_empty_dict(github_issue):
        raise InputContractError(
            "GitHub runs must include both non-empty `github_trigger` and `github_issue` objects"
        )

    has_issue_number = bool(github_issue.get("issue_number") or github_issue.get("number"))
    has_title = bool(github_issue.get("title"))
    trigger_repo = (github_trigger or {}).get("repo") or (github_trigger or {}).get("repository") or {}
    has_repo = bool(
        github_issue.get("repo_full_name")
        or github_issue.get("full_name")
        or trigger_repo.get("full_name")
    )

    missing: list[str] = []
    if not has_issue_number:
        missing.append("issue_number|number")
    if not has_title:
        missing.append("title")
    if not has_repo:
        missing.append("repo_full_name|full_name")

    if missing:
        raise InputContractError(
            "`github_issue` is missing required fields: " + ", ".join(missing)
        )


def validate_run_start_inputs(initial_state: dict[str, Any] | None) -> dict[str, Any]:
    """
    Validate and normalize run-start state.

    Contract (phase2.v1):
    - state must be a non-empty dict
    - must carry either:
      1) a non-empty `_trigger` envelope with core signal fields, OR
      2) GitHub normalized shape: `github_trigger` + `github_issue`
    """
    if not _is_non_empty_dict(initial_state):
        raise InputContractError(
            "Run start requires explicit inputs. Provide `_trigger` or GitHub normalized input state."
        )

    state: dict[str, Any] = deepcopy(initial_state)
    has_trigger = _is_non_empty_dict(state.get("_trigger"))
    has_github = _is_non_empty_dict(state.get("github_trigger")) or _is_non_empty_dict(state.get("github_issue"))

    if not has_trigger and not has_github:
        raise InputContractError(
            "Run start input contract not satisfied. Expected `_trigger` or `github_trigger`/`github_issue`."
        )

    if has_trigger:
        _validate_trigger_shape(state["_trigger"])
        shape = "trigger"
    else:
        _validate_github_shape(state)
        shape = "github"

    state["__input_contract"] = {
        "version": "phase2.v1",
        "status": "validated",
        "shape": shape,
    }
    return state
