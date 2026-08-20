"""Versioned enforcement-capability contract for ConductGuard rules."""
from __future__ import annotations

from typing import Any

CONTRACT_VERSION = 1
SURFACES = ("proxy", "hook", "mcp", "runtime")
STATUSES = frozenset({"hard", "conditional", "advisory", "not_supported"})
BLOCKING_ACTIONS = frozenset({"block"})
NON_BLOCKING_ACTIONS = frozenset({"audit", "audited", "inject", "warn"})
# `approval` is intentionally in neither set: it halts execution until a human
# decides, so it can legitimately claim `hard` on runtime/hook/mcp surfaces
# (the resume plumbing landed in commits 2fb824e / b4df3b9 / 8b8d771).


class EnforcementMetadataError(ValueError):
    """Raised when a rule makes an invalid enforcement claim."""


def is_hook_applicable_rule(rule: dict[str, Any]) -> bool:
    """Return whether hook clients can preserve and evaluate this rule."""
    if rule.get("match_mcp_server") is not None:
        return False
    return any(
        rule.get(field) is not None
        for field in (
            "match_tool",
            "match_ai_tool",
            "match_pattern",
            "match_path_pattern",
        )
    )


def rule_personas(rule: dict[str, Any]) -> set[str]:
    """Normalize legacy persona/persona_affinity fields."""
    value = rule.get("persona")
    if value is None:
        value = rule.get("persona_affinity", ["agent", "proxy"])
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return set()


def validate_enforcement_metadata(rule: dict[str, Any]) -> None:
    """Validate one rule's strict rule-level enforcement contract."""
    rule_id = rule.get("id") or rule.get("rule_id") or "(unknown)"
    metadata = rule.get("enforcement")
    if not isinstance(metadata, dict):
        raise EnforcementMetadataError(f"{rule_id}: enforcement must be an object")
    if metadata.get("version") != CONTRACT_VERSION:
        raise EnforcementMetadataError(
            f"{rule_id}: enforcement.version must be {CONTRACT_VERSION}"
        )

    for surface in SURFACES:
        status = metadata.get(surface)
        if status not in STATUSES:
            raise EnforcementMetadataError(
                f"{rule_id}: enforcement.{surface} must be one of {sorted(STATUSES)}"
            )

    guarantee = metadata.get("guarantee")
    if not isinstance(guarantee, str) or not guarantee.strip():
        raise EnforcementMetadataError(f"{rule_id}: enforcement.guarantee must be nonempty")

    requires = metadata.get("requires")
    limitations = metadata.get("known_limitations")
    for field, value in (("requires", requires), ("known_limitations", limitations)):
        if not isinstance(value, list) or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise EnforcementMetadataError(
                f"{rule_id}: enforcement.{field} must be a list of nonempty strings"
            )
    if "conditional" in (metadata[surface] for surface in SURFACES) and not requires:
        raise EnforcementMetadataError(
            f"{rule_id}: conditional claims require at least one named dependency"
        )

    action = rule.get("action")
    if action in NON_BLOCKING_ACTIONS and any(
        metadata[surface] == "hard" for surface in SURFACES
    ):
        raise EnforcementMetadataError(
            f"{rule_id}: action '{action}' cannot claim hard blocking"
        )

    personas = rule_personas(rule)
    if "proxy" not in personas and metadata["proxy"] != "not_supported":
        raise EnforcementMetadataError(
            f"{rule_id}: proxy claim requires proxy persona applicability"
        )
    if "agent" not in personas and any(
        metadata[surface] != "not_supported" for surface in ("hook", "mcp", "runtime")
    ):
        raise EnforcementMetadataError(
            f"{rule_id}: hook/MCP/runtime claims require agent persona applicability"
        )

    proxy_matcher = any(
        rule.get(field) is not None
        for field in ("match_provider", "match_model", "match_prompt")
    ) or (rule.get("match_pattern") is not None and not rule.get("match_tool"))
    if metadata["proxy"] != "not_supported" and not proxy_matcher:
        raise EnforcementMetadataError(
            f"{rule_id}: proxy cannot evaluate this rule's current matcher shape"
        )

    if rule.get("match_ai_tool") and metadata["mcp"] != "not_supported":
        raise EnforcementMetadataError(
            f"{rule_id}: MCP guard_check does not evaluate match_ai_tool"
        )
    if rule.get("match_mcp_server") and metadata["mcp"] != "not_supported":
        raise EnforcementMetadataError(
            f"{rule_id}: MCP guard_check does not evaluate match_mcp_server"
        )


def validate_pack(pack: dict[str, Any], *, source: str = "(pack)") -> None:
    """Validate every rule in one decoded skill-pack document."""
    rules = pack.get("rules")
    if not isinstance(rules, list):
        raise EnforcementMetadataError(f"{source}: rules must be a list")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            raise EnforcementMetadataError(f"{source}: each rule must be an object")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise EnforcementMetadataError(f"{source}: each rule requires an id")
        if rule_id in seen:
            raise EnforcementMetadataError(f"{source}: duplicate rule id {rule_id}")
        seen.add(rule_id)
        validate_enforcement_metadata(rule)


def conservative_custom_enforcement(rule: dict[str, Any]) -> dict[str, Any]:
    """Generate a non-overclaiming contract for legacy custom rules."""
    action = rule.get("action", "audit")
    status = "conditional" if action == "block" else "advisory"
    has_agent_matcher = any(
        rule.get(field) is not None
        for field in ("match_tool", "match_pattern", "match_path_pattern")
    )
    return {
        "version": CONTRACT_VERSION,
        "proxy": "not_supported",
        "hook": status if has_agent_matcher else "advisory",
        "mcp": status if has_agent_matcher and not rule.get("match_ai_tool") else "not_supported",
        "runtime": "conditional"
        if has_agent_matcher and (
            not rule.get("match_tool")
            or {"*", "workflow", "agent"}
            & {item.strip() for item in str(rule.get("match_tool", "")).split(",")}
        )
        else "not_supported",
        "guarantee": (
            "Custom rule is evaluated only on governed surfaces that receive matching "
            "structured tool input; no capability is assumed for legacy metadata."
        ),
        "requires": [
            "The relevant Guard hook, MCP guard_check integration, or workflow runtime is enabled",
            "The governed surface supplies matcher-compatible tool input",
        ],
        "known_limitations": [
            "Legacy custom rules do not imply proxy coverage",
            "Content or semantics absent from supplied tool input cannot be inspected",
        ],
    }
