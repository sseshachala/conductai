"""
Logic block executor.

Evaluates conditions and routes execution to pass/fail branches.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json
import re

import structlog

log = structlog.get_logger(__name__)


def _evaluate_condition_jinja(raw: str, state: dict) -> str | None:
    """
    Try evaluating a Jinja2 condition expression against the state.
    Returns the rendered string ('True'/'False'/etc.) or None on failure.
    Handles expressions like {{triage.is_real == false}} and
    {{_trigger.severity == 'critical' or _trigger.severity == 'high'}}.
    """
    try:
        import jinja2
        env = jinja2.Environment(undefined=jinja2.Undefined)
        rendered = env.from_string(raw).render(**state).strip()
        # If the template contained no Jinja2 tags, rendered == raw — skip
        if rendered == raw:
            return None
        return rendered
    except Exception:
        return None


def _execute_logic(block: dict, state: dict) -> dict:
    """
    Evaluate a condition and return route: 'pass' or 'fail'.

    Checks (in order):
    1. Explicit condition expression in block config
       - Jinja2 evaluation: {{triage.is_real == false}} → 'True'/'False'
       - Equality expression: "value == true/false" evaluated directly
       - Keyword-based: pass/success/true -> pass; fail/error/false -> fail
    2. exit_code == 0 from last shell output
    3. Keywords 'pass', 'success', 'true', '0' in last output
    """
    from app.runtime.executor import _resolve_refs

    config = block["data"].get("config", {})
    raw_condition = config.get("condition", "")
    # Try Jinja2 evaluation first (handles {{expr == value}} patterns)
    jinja_result = _evaluate_condition_jinja(raw_condition, state)
    if jinja_result is not None:
        r = jinja_result.strip().lower()
        if r in ("true", "1", "yes", "pass", "success"):
            return {"route": "pass", "condition": raw_condition, "evaluated_on": jinja_result}
        if r in ("false", "0", "no", "fail", "error"):
            return {"route": "fail", "condition": raw_condition, "evaluated_on": jinja_result}
    condition_expr = _resolve_refs(raw_condition, state)
    last_output = str(state.get("__last_output", "")).lower()

    # If config has an explicit condition expression, evaluate it
    if condition_expr:
        cond_stripped = condition_expr.strip()
        cond_lower = cond_stripped.lower()

        # Handle equality expressions: "<value> == true/false" or "<value> == <value>"
        eq_match = re.match(r"^(.+?)\s*==\s*(.+)$", cond_stripped, re.IGNORECASE)
        if eq_match:
            lhs = eq_match.group(1).strip().lower()
            rhs = eq_match.group(2).strip().lower()
            # Normalise Python/JSON booleans
            lhs_val = lhs in ("true", "1", "yes")  if lhs in ("true", "false", "1", "0", "yes", "no") else lhs
            rhs_val = rhs in ("true", "1", "yes") if rhs in ("true", "false", "1", "0", "yes", "no") else rhs
            matched = lhs_val == rhs_val
            route = "pass" if matched else "fail"
            return {"route": route, "condition": condition_expr, "evaluated_on": f"{lhs} == {rhs}"}

        # Keyword-only expressions
        if any(k in cond_lower for k in ("fail", "error")):
            return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}
        if cond_lower in ("true", "pass", "success"):
            return {"route": "pass", "condition": condition_expr, "evaluated_on": cond_lower}
        if cond_lower in ("false",):
            return {"route": "fail", "condition": condition_expr, "evaluated_on": cond_lower}

    # Check exit_code in last output (JSON blob from run_shell)
    try:
        last_json = json.loads(state.get("__last_output", "{}"))
        if isinstance(last_json, dict):
            exit_code = last_json.get("exit_code")
            if exit_code is not None:
                route = "pass" if int(exit_code) == 0 else "fail"
                return {"route": route, "condition": condition_expr, "exit_code": exit_code}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Keyword match on last output string
    if any(k in last_output for k in ("pass", "success", "true", "all tests passed", "exit code 0")):
        return {"route": "pass", "condition": condition_expr, "evaluated_on": last_output[:200]}
    if any(k in last_output for k in ("fail", "error", "false", "exception", "traceback")):
        return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}

    # Default: fail (fail-closed — ambiguous output is not a success signal)
    return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}
