"""MCP guard_check honours each rule's enforcement contract.

Surface-scoped rules (``match_ai_tool``) declare ``mcp: not_supported`` because
the MCP PEP cannot evaluate the caller's AI tool. Evaluating them anyway made
claude.ai / Codex Desktop / unknown-surface rules fire for every MCP caller.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.modules.guard.routers.mcp import _match_policy

_BASE_PACK = Path(__file__).resolve().parents[2] / "app/modules/guard/skill_packs/conduct-base.json"


def _rule(rule_id, *, mcp, action="block", **match):
    return {
        "rule_id": rule_id,
        "match_tool": "shell",
        "action": action,
        "gates": ["action"],
        "enforcement": {"version": 1, "hook": "conditional", "mcp": mcp},
        **match,
    }


def test_mcp_pep_skips_rules_marked_not_supported():
    rules = [_rule("chat-only", mcp="not_supported", match_ai_tool="claude-ai")]
    assert _match_policy("bash", {"command": "ls"}, rules, pep="mcp") is None


def test_mcp_pep_still_applies_supported_rules():
    rules = [
        _rule("chat-only", mcp="not_supported", match_ai_tool="claude-ai"),
        _rule("everyone", mcp="conditional", action="warn"),
    ]
    matched = _match_policy("bash", {"command": "ls"}, rules, pep="mcp")
    assert matched is not None and matched["rule_id"] == "everyone"


def test_rules_without_contract_still_apply_under_mcp_pep():
    rule = {"rule_id": "legacy", "match_tool": "bash", "action": "block", "gates": ["action"]}
    assert _match_policy("bash", {}, [rule], pep="mcp")["rule_id"] == "legacy"


def test_no_pep_keeps_previous_behaviour():
    rules = [_rule("chat-only", mcp="not_supported", match_ai_tool="claude-ai")]
    assert _match_policy("bash", {}, rules)["rule_id"] == "chat-only"


def test_base_pack_surface_rules_do_not_fire_over_mcp():
    pack = json.loads(_BASE_PACK.read_text())
    rules = [
        {**r, "rule_id": r["id"], "gates": r.get("gates") or ["action"]}
        for r in pack["rules"]
        if r.get("match_ai_tool")
    ]
    assert rules, "conduct-base should ship surface-scoped rules"
    for tool, inp in (("bash", {"command": "git status"}), ("write_file", {"file_path": "a.py"})):
        matched = _match_policy(tool, inp, rules, pep="mcp")
        assert matched is None, matched and matched["rule_id"]
