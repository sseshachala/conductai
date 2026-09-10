"""#1733 / #1750 Phase B — PolicyOut carries gates + retained prose.

Verifies that the API surfaces the three fields the Policies UI needs:
- ``gates`` (locked enum [action, prompt, response]) — derived on projection
- ``guarantee`` (hand-authored trust prose, retained per reviewer edit 4)
- ``known_limitations`` (hand-authored operational caveats, retained)
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.modules.guard.routers.policies import (
    PolicyOut,
    _custom_to_out,
    _pack_rule_to_out,
)


def test_pack_rule_to_out_stamps_gates_from_persona_default():
    rule = {"id": "r-a", "action": "block", "persona": "agent"}
    out = _pack_rule_to_out(rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert isinstance(out, PolicyOut)
    assert out.gates == ["action"]


def test_pack_rule_to_out_populates_derived_surface_status():
    """#1755 Slice 2 — every PolicyOut carries derived_<surface> for all four PEPs."""
    action_rule = {"id": "act", "action": "block", "gates": ["action"]}
    out = _pack_rule_to_out(action_rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.derived_mcp == "hard"
    assert out.derived_hook == "hard"
    assert out.derived_runtime == "hard"
    assert out.derived_proxy == "not_supported"


def test_pack_rule_to_out_derived_proxy_hard_for_prompt_gate_rule():
    prompt_rule = {"id": "prompt-x", "action": "block", "gates": ["prompt"]}
    out = _pack_rule_to_out(prompt_rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.derived_proxy == "hard"
    assert out.derived_mcp == "not_supported"


def test_pack_rule_to_out_stamps_gates_from_proxy_persona():
    rule = {"id": "r-p", "action": "warn", "persona": "proxy"}
    out = _pack_rule_to_out(rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.gates == ["prompt"]


def test_pack_rule_to_out_stamps_explicit_gates_over_persona():
    """Rule authors that set gates explicitly (e.g. new response-gate rule)
    have their choice honored — persona derivation only fills the gap."""
    rule = {"id": "r-r", "action": "block", "persona": "proxy", "gates": ["response"]}
    out = _pack_rule_to_out(rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.gates == ["response"]


def test_pack_rule_to_out_exposes_guarantee_and_known_limitations():
    rule = {
        "id": "hipaa-ssn",
        "action": "block",
        "persona": "agent",
        "enforcement": {
            "guarantee": "Blocks SSN writes at the file boundary.",
            "known_limitations": [
                "MCP guard_check must be called by the agent",
                "Zip-encoded uploads bypass the pattern",
            ],
        },
    }
    out = _pack_rule_to_out(rule, "conduct-hipaa", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.guarantee == "Blocks SSN writes at the file boundary."
    assert len(out.known_limitations) == 2
    assert "MCP guard_check must be called" in out.known_limitations[0]


def test_pack_rule_to_out_defaults_prose_when_enforcement_missing():
    rule = {"id": "r-x", "action": "audit"}
    out = _pack_rule_to_out(rule, "conduct-base", datetime.now(timezone.utc), uuid.uuid4(), None)
    assert out.guarantee is None
    assert out.known_limitations == []


def test_custom_to_out_stamps_gates_and_prose():
    row = MagicMock()
    row.rule_id = "custom-a"
    row.workspace_id = uuid.uuid4()
    row.persona = "agent"
    row.enabled = True
    row.created_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    row.body = {
        "action": "warn",
        "enforcement": {
            "guarantee": "Warns on internal repo writes.",
            "known_limitations": ["Case-insensitive path match only"],
        },
    }
    out = _custom_to_out(row)
    assert out.gates == ["action"]
    assert out.guarantee == "Warns on internal repo writes."
    assert out.known_limitations == ["Case-insensitive path match only"]
