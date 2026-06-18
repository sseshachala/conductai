"""Pure policy enforcer — no I/O, no network. Shared by daemon HTTP handler."""
from __future__ import annotations
import json
import re


def check_policy(
    tool_name: str,
    tool_input: dict,
    rules: list[dict],
    tokens_before: int = 0,
) -> tuple[dict | None, str, str | None, str | None]:
    """Return (rule, action, rule_id, message) or (None, 'allow', None, None)."""
    input_text  = json.dumps(tool_input)
    path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in [t.strip() for t in match_tool.split(",")]:
                continue

        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not re.search(pattern, input_text, re.IGNORECASE):
                    continue
            except re.error:
                continue

        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not any(re.search(path_pattern, f, re.IGNORECASE) for f in path_fields if f):
                    continue
            except re.error:
                continue

        min_tokens = rule.get("match_tokens_before_gt")
        if min_tokens is not None and tokens_before <= int(min_tokens):
            continue

        action  = rule.get("action", "audit")
        rule_id = rule.get("rule_id") or rule.get("id", "unknown")
        message = rule.get("message") or f"Policy violation: {rule_id}"
        return rule, action, rule_id, message

    return None, "allow", None, None
