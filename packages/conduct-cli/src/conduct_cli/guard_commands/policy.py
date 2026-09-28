"""Guard CLI: policy."""
from __future__ import annotations

from conduct_cli.tool_groups import expand_match_tool
import json
import json as _json
import re as _re
import sys

from . import shared as _guard_shared


def _bash_command_words(cmd: str) -> list[str]:
    """First token of each pipeline / conditional / semicolon-separated segment.

    Argument bodies, heredoc contents, and quoted strings are ignored — so a
    privilege-escalation matcher firing on the literal word inside a body
    payload (issue body, commit message, file write) is no longer possible.
    Returns lower-cased command words for case-insensitive matching.
    """
    import shlex as _shlex
    words: list[str] = []
    if not cmd:
        return words
    # Split on bash control operators (||, &&, |, ;, & and bg/fg keywords).
    for segment in _re.split(r"\|\||&&|[|;&\n]+|\bthen\b|\belse\b|\bdo\b", cmd):
        seg = segment.strip()
        if not seg:
            continue
        try:
            parts = _shlex.split(seg)
        except ValueError:
            continue
        if parts:
            # Strip env-var prefixes (FOO=bar bin baz → bin)
            for p in parts:
                if "=" in p and not p.startswith(("-", "/")):
                    continue
                words.append(p.lower())
                break
    return words


def _check_policy(tool_name, tool_input, tokens_before=0, ai_tool=""):
    """Return (matched_rule, action, rule_id, message) or (None, 'allow', None, None)."""
    policy = _load_policy()
    if not policy.get("rules"):
        return None, "allow", None, None

    rules      = policy.get("rules", [])
    input_text = _json.dumps(tool_input)
    path_fields = [str(tool_input.get(f, "")) for f in ["file_path", "path", "command"]]
    # Extract command words only when bash is involved — empty list for other tools.
    command_words = (
        _bash_command_words(str(tool_input.get("command", "")))
        if tool_name.lower() == "bash" else []
    )

    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_name not in expand_match_tool(match_tool):
                continue
        match_ai = rule.get("match_ai_tool")
        if match_ai:
            surfaces = [s.strip().lower() for s in match_ai.split(",")]
            if not any(s in ai_tool.lower() for s in surfaces):
                continue
        # New: structural match against the actual binary being invoked.
        # Single string or list of strings; case-insensitive equality.
        cw = rule.get("match_command_word")
        if cw:
            deny = [w.lower() for w in (cw if isinstance(cw, list) else [cw])]
            if not any(w in deny for w in command_words):
                continue
        pattern = rule.get("match_pattern")
        if pattern:
            try:
                if not _re.search(pattern, input_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue
        path_pattern = rule.get("match_path_pattern")
        if path_pattern:
            try:
                if not any(_re.search(path_pattern, f, _re.IGNORECASE) for f in path_fields if f):
                    continue
            except _re.error:
                continue
        min_tokens = rule.get("match_tokens_before_gt")
        if min_tokens is not None:
            if tokens_before <= int(min_tokens):
                continue
        action  = rule.get("action", "audit")
        rule_id = rule.get("rule_id", "unknown")
        message = rule.get("message") or f"Policy violation: {rule_id}"
        return rule, action, rule_id, message

    return None, "allow", None, None


def _save_policy(policy: dict, workspace_id: str | None = None):
    _guard_shared.GUARD_DIR.mkdir(parents=True, exist_ok=True)
    _guard_shared.POLICY_PATH.write_text(json.dumps(policy, indent=2))


def _load_policy(workspace_id: str | None = None) -> dict:
    try:
        return json.loads(_guard_shared.POLICY_PATH.read_text())
    except Exception:
        return {"rules": []}


def cmd_guard_lint(args):
    """Validate the local policy file and report errors / warnings."""
    import json as _json, re as _re

    policy_path = getattr(args, "file", None)
    if policy_path:
        from pathlib import Path as _Path
        p = _Path(policy_path).expanduser().resolve()
        if not p.exists():
            print(f"  {_guard_shared.RED}File not found: {p}{_guard_shared.RESET}")
            sys.exit(1)
        raw = p.read_text()
    else:
        policy = _load_policy()
        raw = None

    if raw is not None:
        try:
            policy = _json.loads(raw)
        except Exception:
            try:
                import yaml as _yaml
                policy = _yaml.safe_load(raw)
            except Exception as e:
                print(f"  {_guard_shared.RED}Cannot parse file: {e}{_guard_shared.RESET}")
                sys.exit(1)

    rules     = policy.get("rules", [])
    fail_mode = policy.get("fail_mode")

    # ── local lint (no API call needed) ──────────────────────────────────────
    VALID_ACTIONS    = {"block", "warn", "audit", "approval", "inject"}
    VALID_FAIL_MODES = {"fail_open", "fail_closed"}
    MATCH_FIELDS     = {"match_tool", "match_pattern", "match_path_pattern",
                        "match_command_word", "match_tokens_before_gt"}

    errors: list[dict] = []
    warnings: list[dict] = []
    seen_ids: set[str] = set()

    if fail_mode and fail_mode not in VALID_FAIL_MODES:
        errors.append({"rule_id": "(policy)", "field": "fail_mode",
                       "message": f"must be one of: {', '.join(sorted(VALID_FAIL_MODES))}"})

    for i, rule in enumerate(rules):
        rid = rule.get("rule_id") or rule.get("id") or f"(rule[{i}])"
        if not rule.get("rule_id") and not rule.get("id"):
            errors.append({"rule_id": rid, "field": "rule_id", "message": "rule_id is required"})
        if rid in seen_ids:
            errors.append({"rule_id": rid, "field": "rule_id", "message": f"Duplicate rule_id '{rid}'"})
        seen_ids.add(rid)

        action = rule.get("action")
        if not action:
            errors.append({"rule_id": rid, "field": "action", "message": "action is required"})
        elif action not in VALID_ACTIONS:
            errors.append({"rule_id": rid, "field": "action",
                           "message": f"'{action}' must be one of: {', '.join(sorted(VALID_ACTIONS))}"})

        for rf in ("match_pattern", "match_path_pattern"):
            val = rule.get(rf)
            if val:
                try:
                    _re.compile(val)
                except _re.error as e:
                    errors.append({"rule_id": rid, "field": rf, "message": f"Invalid regex: {e}"})

        if not any(rule.get(f) for f in MATCH_FIELDS):
            warnings.append({"rule_id": rid, "field": "match_*",
                             "message": "No match condition — rule fires on every tool call"})

        tokens = rule.get("match_tokens_before_gt")
        if tokens is not None and (not isinstance(tokens, int) or tokens <= 0):
            errors.append({"rule_id": rid, "field": "match_tokens_before_gt",
                           "message": "must be a positive integer"})

    # ── output ────────────────────────────────────────────────────────────────
    print(f"\n  {_guard_shared.BOLD}Policy lint{_guard_shared.RESET} — {len(rules)} rule(s)\n")

    if not errors and not warnings:
        print(f"  {_guard_shared.GREEN}No issues found{_guard_shared.RESET}\n")
        return

    for e in errors:
        print(f"  {_guard_shared.RED}ERROR{_guard_shared.RESET}  [{e['rule_id']}] {e['field']}: {e['message']}")
    for w in warnings:
        print(f"  {_guard_shared.YELLOW}WARN{_guard_shared.RESET}   [{w['rule_id']}] {w['field']}: {w['message']}")

    print()
    if errors:
        sys.exit(1)
