"""#1751 PR 2 — derive_surface_status.

Reads rule.gates × PEP_CAPABILITIES[surface] and returns "hard" if there's
an overlap, "not_supported" otherwise. Legacy hand-authored "conditional"
and "advisory" statuses are OUT of scope — this helper reports only the
declared-capability status per Property 8.
"""
from __future__ import annotations

from app.modules.guard.enforcement import derive_surface_status


# ── proxy surface — evaluates prompt + response gates ──────────────────

def test_proxy_supports_prompt_gate_rule():
    rule = {"gates": ["prompt"]}
    assert derive_surface_status(rule, "proxy") == "hard"


def test_proxy_supports_response_gate_rule():
    rule = {"gates": ["response"]}
    assert derive_surface_status(rule, "proxy") == "hard"


def test_proxy_does_not_support_pure_action_gate_rule():
    rule = {"gates": ["action"]}
    assert derive_surface_status(rule, "proxy") == "not_supported"


def test_proxy_supports_dual_gate_rule_on_any_overlap():
    """[action, prompt] rule → proxy sees the prompt half."""
    rule = {"gates": ["action", "prompt"]}
    assert derive_surface_status(rule, "proxy") == "hard"


# ── mcp / runtime / hook — evaluate action gate only ───────────────────

def test_mcp_supports_action_gate():
    rule = {"gates": ["action"]}
    assert derive_surface_status(rule, "mcp") == "hard"


def test_mcp_does_not_support_prompt_gate():
    rule = {"gates": ["prompt"]}
    assert derive_surface_status(rule, "mcp") == "not_supported"


def test_runtime_supports_action_gate():
    rule = {"gates": ["action"]}
    assert derive_surface_status(rule, "runtime") == "hard"


def test_hook_supports_action_gate():
    rule = {"gates": ["action"]}
    assert derive_surface_status(rule, "hook") == "hard"


# ── unknown surfaces + missing gates ──────────────────────────────────

def test_unknown_surface_is_not_supported():
    rule = {"gates": ["action"]}
    assert derive_surface_status(rule, "carrier-pigeon") == "not_supported"


def test_legacy_rule_without_gates_derives_from_persona():
    """When gates aren't stamped, derive_gates fills in from persona."""
    agent_rule = {"persona": "agent"}
    proxy_rule = {"persona": "proxy"}
    assert derive_surface_status(agent_rule, "mcp") == "hard"
    assert derive_surface_status(agent_rule, "proxy") == "not_supported"
    assert derive_surface_status(proxy_rule, "proxy") == "hard"
    assert derive_surface_status(proxy_rule, "mcp") == "not_supported"


def test_no_conditional_or_advisory_returned():
    """PR 2 scope: only 'hard' or 'not_supported'. Conditional and advisory
    stay hand-authored on rule.enforcement until Phase D."""
    for gates in (["action"], ["prompt"], ["response"], ["action", "prompt"], []):
        for surface in ("mcp", "proxy", "runtime", "hook", "unknown"):
            status = derive_surface_status({"gates": gates}, surface)
            assert status in ("hard", "not_supported"), (
                f"surface={surface} gates={gates} → {status}"
            )
