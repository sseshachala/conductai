"""ConductGuard policies — rule lint endpoint (POST /guard/policies/lint)."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends
from app.core.auth import (
    get_workspace_id,
    require_permission,
)
from app.modules.guard.routers.policies_schemas import (
    LintIssue,
    LintRequest,
    LintResponse,
)
from app.modules.guard.routers.policies_helpers import (
    _VALID_ACTIONS,
)

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])


_VALID_FAIL_MODES = {"fail_open", "fail_closed"}


_MATCH_FIELDS = {"match_tool", "match_pattern", "match_path_pattern", "match_command_word", "match_tokens_before_gt"}


def _lint_rules(rules: list[dict], fail_mode: Optional[str]) -> tuple[list[LintIssue], list[LintIssue]]:
    import re as _re
    errors: list[LintIssue] = []
    warnings: list[LintIssue] = []
    seen_ids: set[str] = set()

    if fail_mode and fail_mode not in _VALID_FAIL_MODES:
        errors.append(LintIssue(rule_id="(policy)", field="fail_mode",
                                message=f"fail_mode must be one of: {', '.join(sorted(_VALID_FAIL_MODES))}"))

    for i, rule in enumerate(rules):
        rid = rule.get("rule_id") or rule.get("id") or f"(rule[{i}])"

        if not rule.get("rule_id") and not rule.get("id"):
            errors.append(LintIssue(rule_id=rid, field="rule_id", message="rule_id is required"))

        if rid in seen_ids:
            errors.append(LintIssue(rule_id=rid, field="rule_id", message=f"Duplicate rule_id '{rid}'"))
        seen_ids.add(rid)

        action = rule.get("action")
        if not action:
            errors.append(LintIssue(rule_id=rid, field="action", message="action is required"))
        elif action not in _VALID_ACTIONS:
            errors.append(LintIssue(rule_id=rid, field="action",
                                    message=f"action '{action}' must be one of: {', '.join(sorted(_VALID_ACTIONS))}"))

        for regex_field in ("match_pattern", "match_path_pattern"):
            val = rule.get(regex_field)
            if val:
                try:
                    _re.compile(val)
                except _re.error as e:
                    errors.append(LintIssue(rule_id=rid, field=regex_field,
                                            message=f"Invalid regex: {e}"))

        if not any(rule.get(f) for f in _MATCH_FIELDS):
            warnings.append(LintIssue(rule_id=rid, field="match_*",
                                      message="No match condition — rule will match every tool call"))

        tokens = rule.get("match_tokens_before_gt")
        if tokens is not None and (not isinstance(tokens, int) or tokens <= 0):
            errors.append(LintIssue(rule_id=rid, field="match_tokens_before_gt",
                                    message="match_tokens_before_gt must be a positive integer"))

    return errors, warnings


@router.post("/lint", response_model=LintResponse)
def lint_policy(
    body: LintRequest,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Validate a policy (rules list) and return errors + warnings. No DB writes."""
    errors, warnings = _lint_rules(body.rules, body.fail_mode)
    return LintResponse(errors=errors, warnings=warnings)
