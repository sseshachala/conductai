"""JSON Guard pack → Cedar text export.

Reverse of mapper.py. Takes a Guard pack in our native JSON format and
emits the equivalent Cedar text syntax. For customer readability and
policy inspection. Runtime evaluation still uses the JSON format.
"""
from __future__ import annotations

from typing import Any


PERSONA_TO_TYPE = {
    "security": "SecurityAdmin",
    "developer": "Developer",
    "agent": "Agent",
    "viewer": "Viewer",
    "admin": "Admin",
}

ACTION_TO_EFFECT = {
    "block": "forbid",
    "warn": "permit",
    "audit": "permit",
    "approval": "permit",
    "inject": "permit",
}

ACTION_TO_ADVICE = {
    "warn": "warn",
    "audit": None,       # audit is the default effect, no advice needed
    "block": None,       # forbid maps directly
    "approval": "approval",
    "inject": "inject",
}


def rule_to_cedar_text(rule: dict[str, Any]) -> str:
    """Render one Guard rule as a Cedar policy in text syntax."""
    lines: list[str] = []

    annotations = _build_annotations(rule)
    lines.extend(annotations)

    action = rule.get("action", "audit")
    effect = ACTION_TO_EFFECT.get(action, "permit")

    lines.append(f"{effect} (")
    lines.append(f"    {_render_principal(rule)},")
    lines.append(f"    {_render_action(rule)},")
    lines.append("    resource")
    lines.append(")")

    when_clauses = _build_when_clauses(rule)
    if when_clauses:
        lines.append("when {")
        for i, clause in enumerate(when_clauses):
            suffix = " &&" if i < len(when_clauses) - 1 else ""
            lines.append(f"    {clause}{suffix}")
        lines.append("}")

    return "\n".join(lines) + ";"


def _build_annotations(rule: dict[str, Any]) -> list[str]:
    """Emit Cedar @annotation lines for all supported metadata fields."""
    out: list[str] = []
    rid = rule.get("id") or rule.get("rule_id")
    if rid:
        out.append(f'@id({_quote(rid)})')

    desc = rule.get("description")
    if desc:
        out.append(f'@description({_quote(desc)})')

    message = rule.get("message")
    if message:
        out.append(f'@message({_quote(message)})')

    recommendation = rule.get("recommendation")
    if recommendation:
        out.append(f'@recommendation({_quote(recommendation)})')

    severity = rule.get("severity")
    if severity:
        out.append(f'@severity({_quote(severity)})')

    iso_control = rule.get("iso_control")
    if iso_control:
        out.append(f'@iso_control({_quote(iso_control)})')

    frameworks = rule.get("frameworks")
    if frameworks:
        if isinstance(frameworks, str):
            frameworks = [frameworks]
        quoted = ", ".join(_quote(f) for f in frameworks)
        out.append(f'@compliance({quoted})')

    # Cedar-side advice for actions that are permit-shaped in Cedar
    advice = ACTION_TO_ADVICE.get(rule.get("action", "audit"))
    if advice:
        out.append(f'@advice({_quote(advice)})')

    source_pack = rule.get("source_pack")
    if source_pack:
        out.append(f'@source_pack({_quote(source_pack)})')

    return out


def _render_principal(rule: dict[str, Any]) -> str:
    """Render the principal clause based on persona_affinity."""
    affinity = rule.get("persona_affinity") or []
    if not affinity or len(affinity) > 1:
        # Multi-persona or no persona means unrestricted principal
        return "principal"
    persona = affinity[0]
    persona_type = PERSONA_TO_TYPE.get(persona)
    if persona_type:
        return f"principal is {persona_type}"
    return "principal"


def _render_action(rule: dict[str, Any]) -> str:
    """Render the action clause based on match_tool."""
    tool = (rule.get("match_tool") or "*").strip()
    if tool == "*" or not tool:
        return "action"
    tools = [t.strip() for t in tool.split(",") if t.strip()]
    if len(tools) == 1:
        return f'action == Action::"{tools[0]}"'
    entities = ", ".join(f'Action::"{t}"' for t in tools)
    return f"action in [{entities}]"


def _build_when_clauses(rule: dict[str, Any]) -> list[str]:
    """Assemble when-clause expressions from matcher fields."""
    clauses: list[str] = []

    pattern = rule.get("match_pattern")
    if pattern:
        clauses.append(f"context.prompt matches {_quote(pattern)}")

    path_pattern = rule.get("match_path_pattern")
    if path_pattern:
        clauses.append(f"context.path matches {_quote(path_pattern)}")

    tokens = rule.get("match_tokens_before_gt")
    if tokens is not None:
        clauses.append(f"context.tokens_before > {int(tokens)}")

    risk_tier = rule.get("match_agent_risk_tier")
    if risk_tier:
        clauses.append(f"context.risk_tier == {_quote(risk_tier)}")

    ai_tool = rule.get("match_ai_tool")
    if ai_tool:
        clauses.append(f"context.ai_tool == {_quote(ai_tool)}")

    mcp_server = rule.get("match_mcp_server")
    if mcp_server:
        clauses.append(f"context.mcp_server == {_quote(mcp_server)}")

    model = rule.get("match_model")
    if model:
        clauses.append(f"context.model matches {_quote(model)}")

    return clauses


def _quote(value: Any) -> str:
    """Cedar string literal — double-quoted with backslash escaping."""
    s = str(value)
    s = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'"{s}"'


def pack_to_cedar_text(pack: dict[str, Any]) -> str:
    """Render an entire Guard pack as a Cedar policy file."""
    header_lines = [
        f"// Cedar rendering of Guard pack: {pack.get('slug', 'unknown')}",
        f"// Name:        {pack.get('name', 'Unknown')}",
        f"// Version:     {pack.get('version', 'unknown')}",
        f"// Tier:        {pack.get('tier', 'unknown')}",
    ]
    description = pack.get("description")
    if description:
        header_lines.append(f"// Description: {description}")
    header_lines.append(
        "// NOTE: This is the human-readable Cedar rendering of the pack."
    )
    header_lines.append(
        "// Runtime evaluation uses the JSON representation. Both are semantically equivalent."
    )
    header_lines.append("")

    rules = pack.get("rules", [])
    rule_blocks = [rule_to_cedar_text(r) for r in rules]

    return "\n".join(header_lines) + "\n\n".join(rule_blocks) + "\n"
