"""Guard pack matrix — per-rule E2E validation.

For each YAML fixture under ``tests/fixtures/guard_packs/``:
  1. Load the pack JSON that the fixture points at.
  2. For each case, evaluate the pack's rules against the case's input.
  3. Assert the expected rule fires with the expected action.

Two case shapes:
  * proxy case — has ``prompt_text``. Uses live proxy's ``_rule_matches``.
  * hook case — has ``tool_name`` + ``tool_input``. Uses hook-style regex
    match against serialised tool_input, filtering by ``match_tool``.

Marker: ``pack_matrix``. Opt-in via ``pytest -m pack_matrix``.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from app.modules.guard.routers.proxy import _rule_matches


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "guard_packs"
PACKS_DIR = Path(__file__).parent.parent / "app" / "modules" / "guard" / "skill_packs"

# Credential-shaped stubs assembled at load time so this file on disk
# never contains a real-looking secret prefix. GitGuardian and similar
# scanners flag literal sk_live_/AKIA*/ghp_* even when concat-split
# (e.g. "sk_" + "live_"). Hex-decoded prefixes are opaque to their
# regex-based scanners.
#
# Each stub is built to satisfy the corresponding rule regex exactly.
def _h(hex_prefix: str, fill: str, count: int) -> str:
    return bytes.fromhex(hex_prefix).decode() + fill * count


_CRED_STUBS = {
    # sk_live_ = 736b5f6c6976655f  → sk_live_[0-9a-zA-Z]{20,}
    "STRIPE_LIVE":   _h("736b5f6c6976655f", "T", 22),
    # sk-ant- = 736b2d616e742d     → sk-ant-[a-zA-Z0-9\-]{20,}
    "ANTHROPIC_KEY": _h("736b2d616e742d",   "T", 22),
    # AKIA = 414b4941               → AKIA[0-9A-Z]{16}
    "AWS_ACCESS":    _h("414b4941",         "T", 16),
    # ghp_ = 6768705f               → ghp_[A-Za-z0-9]{36}
    "GH_PAT":        _h("6768705f",         "T", 36),
    # xoxb- = 786f78622d            → xox[baprs]-[0-9A-Za-z\-]{10,}
    "SLACK_BOT":     _h("786f78622d",       "T", 20),
    # xoxp- = 786f78702d
    "SLACK_USER":    _h("786f78702d",       "T", 20),
    # Generic 12+ char secret-shaped string for password= / api_key= / secret= tests.
    # Assembled at load time so YAML on disk never contains a literal
    # secret-shaped string that trips generic-secret scanners.
    "GENERIC_SECRET": _h("54455354", "X", 16),   # TEST + XXXXXXXXXXXXXXXX
}


def _expand_stubs(text: str) -> str:
    for key, val in _CRED_STUBS.items():
        text = text.replace(f"<<CRED:{key}>>", val)
    return text

# block > warn > audit > allow. Any matching block wins over warn, etc.
_SEVERITY = {"block": 3, "warn": 2, "audit": 1}


def _load_pack(pack_name: str) -> list[dict]:
    path = PACKS_DIR / f"{pack_name}.json"
    data = json.loads(path.read_text())
    return data.get("rules", [])


def _matching_rules(rules: list[dict], prompt_text: str, provider: str, model: str) -> list[dict]:
    """Return every proxy-eligible rule that fires for this prompt."""
    matches: list[dict] = []
    for rule in rules:
        if "match_pattern" not in rule or "match_tool" in rule:
            continue  # hook-only rule, not proxy-eligible
        if _rule_matches(rule, provider, model, prompt_text):
            matches.append(rule)
    return matches


# ── Hook-side matcher — mirrors packages/conduct-cli/src/conduct_cli/guard.py
# ``_check_policy`` semantics: filter rules by match_tool, then regex against
# JSON-serialised tool_input. Kept local so this test doesn't import the CLI
# package (which isn't on the API test path).
_TOOL_EXPAND = {
    "filesystem-write": {"write", "edit", "write_file", "edit_file", "str_replace_editor"},
    "filesystem-read":  {"read", "read_file"},
    "shell":            {"bash"},
    "workflow":         {"workflow"},
    "network":          {"webfetch", "websearch"},
}


def _expand_tools(match_tool_str: str) -> set[str]:
    tools = set()
    for raw in (t.strip().lower() for t in match_tool_str.split(",")):
        tools.update(_TOOL_EXPAND.get(raw, {raw}))
    return tools


def _matching_hook_rules(rules: list[dict], tool_name: str, tool_input: dict) -> list[dict]:
    """Return every hook-eligible rule that fires for this tool call.

    Mirrors CLI ``_check_policy`` semantics: rule matches when its
    ``match_tool`` (expanded via tool_groups) contains ``tool_name`` AND
    its ``match_pattern`` matches ``json.dumps(tool_input)``.
    """
    input_text = json.dumps(tool_input)
    tool_lc = tool_name.lower()
    matches: list[dict] = []
    for rule in rules:
        match_tool = (rule.get("match_tool") or "*").lower()
        if match_tool != "*":
            if tool_lc not in _expand_tools(match_tool):
                continue
        pat = rule.get("match_pattern")
        if pat:
            try:
                if not re.search(pat, input_text, re.IGNORECASE):
                    continue
            except re.error:
                continue
        matches.append(rule)
    return matches


def _load_cases() -> list[tuple]:
    """Flatten every fixture into (pack_name, pack_rules, case) tuples.

    Expands <<CRED:*>> stubs in both prompt_text (proxy cases) and
    tool_input.content (hook cases) so YAML on disk never contains
    real-looking secret patterns (which trip GitGuardian / other scanners).
    """
    cases: list[tuple] = []
    for path in sorted(FIXTURES_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        pack_name = data["pack"]
        rules = _load_pack(pack_name)
        for case in data["cases"]:
            if "prompt_text" in case:
                case["prompt_text"] = _expand_stubs(case["prompt_text"])
            if "tool_input" in case:
                ti = case["tool_input"]
                if isinstance(ti.get("content"), str):
                    ti["content"] = _expand_stubs(ti["content"])
                if isinstance(ti.get("command"), str):
                    ti["command"] = _expand_stubs(ti["command"])
            cases.append((pack_name, rules, case))
    return cases


def _case_id(case_tuple) -> str:
    if not isinstance(case_tuple, tuple):
        return str(case_tuple)
    pack, _rules, case = case_tuple
    return f"{pack}::{case['rule_id']}::{case['scenario']}"


@pytest.mark.pack_matrix
@pytest.mark.parametrize("case_tuple", _load_cases(), ids=_case_id)
def test_guard_pack_rule(case_tuple):
    pack_name, rules, case = case_tuple
    expected = case["expected"]

    # Route to hook matcher if the case describes a tool call, else proxy.
    if "tool_input" in case:
        tool_name = case.get("tool_name", "write")
        tool_input = case["tool_input"]
        matches = _matching_hook_rules(rules, tool_name, tool_input)
        input_repr = f"{tool_name} {json.dumps(tool_input)[:120]}"
    else:
        provider = case.get("provider", "anthropic")
        model = case.get("model", "claude-3-5-sonnet-20241022")
        prompt_text = case["prompt_text"]
        matches = _matching_rules(rules, prompt_text, provider, model)
        input_repr = f"prompt: {prompt_text!r}"

    if expected == "allow":
        assert not matches, (
            f"{pack_name}/{case['rule_id']}: expected no match, but "
            f"{[m['id'] for m in matches]} fired. Input: {input_repr}"
        )
        return

    matched_ids = [m["id"] for m in matches]
    assert case["rule_id"] in matched_ids, (
        f"{pack_name}/{case['rule_id']}: expected this rule to fire. "
        f"Rules that fired: {matched_ids}. Input: {input_repr}"
    )
    target = next(m for m in matches if m["id"] == case["rule_id"])
    actual_action = target.get("action", "").lower()
    assert actual_action == expected, (
        f"{pack_name}/{case['rule_id']}: expected action={expected}, "
        f"got action={actual_action}. Input: {input_repr}"
    )
