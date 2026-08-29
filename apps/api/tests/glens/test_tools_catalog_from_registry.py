"""Lens TOOLS (LLM catalog) is derived from default_registry (#1281 wiring
fix). Locks the invariant that adding a ToolDef tagged 'lens' automatically
makes the LLM aware of it, and that hand-tuned detailed descriptions from
the pre-#1281 catalog are preserved verbatim.
"""
from __future__ import annotations

from app.modules.glens.routers.chat import TOOLS, _LEGACY_DESCRIPTIONS
from app.tools.registry import default_registry


def test_tools_matches_registry_lens_tag():
    """Every 'lens'-tagged ToolDef appears in TOOLS, and TOOLS contains only
    those tools (no extras, no leftovers from the old hardcoded list)."""
    registry_names = {t.name for t in default_registry.list(tag="lens")}
    catalog_names = {t["name"] for t in TOOLS}
    assert catalog_names == registry_names, (
        f"catalog vs registry mismatch. "
        f"registry-only: {sorted(registry_names - catalog_names)}. "
        f"catalog-only: {sorted(catalog_names - registry_names)}."
    )


def test_new_read_tools_are_reachable_by_llm():
    """The 12 tools added in the #1281 sweep are in the LLM catalog."""
    expected_new = {
        # Governance rollups (#1295, #1420)
        "get_governance_summary", "get_soc2_status", "get_ai_rollout_status",
        # Batch A (#1413, #1416, #1418, #1419)
        "list_playbooks", "get_playbook",
        "list_machines_sync_state",
        "get_llm_primitives", "get_rate_limits",
        # Batch B (#1414, #1415, #1417, #1296)
        "get_workspace_kpis", "list_discovered_agents",
        "list_credentials", "get_autopilot_activity",
    }
    catalog_names = {t["name"] for t in TOOLS}
    missing = expected_new - catalog_names
    assert not missing, f"Expected new tools missing from LLM catalog: {sorted(missing)}"


def test_legacy_detailed_descriptions_preserved():
    """Tools that had hand-tuned formatting instructions in the pre-#1281
    hardcoded list still carry those descriptions verbatim (protects LLM
    tool-selection behaviour for well-covered questions)."""
    for tool in TOOLS:
        legacy = _LEGACY_DESCRIPTIONS.get(tool["name"])
        if legacy is None:
            continue
        assert tool["description"] == legacy, (
            f"{tool['name']} lost its legacy description "
            f"(catalog: {tool['description'][:60]!r}; expected: {legacy[:60]!r})"
        )


def test_tools_shape_is_llm_ready():
    """Every entry has the name / description / input_schema fields the
    Anthropic + OpenAI tool-use APIs expect."""
    for tool in TOOLS:
        assert isinstance(tool["name"], str) and tool["name"]
        assert isinstance(tool["description"], str) and tool["description"]
        assert isinstance(tool["input_schema"], dict)
        assert tool["input_schema"].get("type") == "object"
