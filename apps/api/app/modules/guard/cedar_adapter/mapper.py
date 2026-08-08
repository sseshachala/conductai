"""Cedar JSON to Guard JSON pack rule mapper."""
from __future__ import annotations

from typing import Any

from app.modules.guard.cedar_adapter.errors import (
    InvalidCedarSyntax,
    UnsupportedCedarFeature,
)


PERSONA_TYPE_MAP = {
    "SecurityAdmin": "security",
    "Security": "security",
    "Developer": "developer",
    "Dev": "developer",
    "Agent": "agent",
    "Viewer": "viewer",
    "Admin": "admin",
}

ADVICE_ACTION_MAP = {
    "warn": "warn",
    "block": "block",
    "audit": "audit",
    "approval": "approval",
    "inject": "inject",
}


def cedar_json_to_rule(policy: dict[str, Any]) -> dict[str, Any]:
    """Convert one Cedar JSON policy to one Guard pack rule."""
    if not isinstance(policy, dict):
        raise InvalidCedarSyntax("Cedar policy must be a JSON object", snippet=str(policy)[:200])

    effect = policy.get("effect")
    if effect not in ("permit", "forbid"):
        raise InvalidCedarSyntax(
            f"Cedar effect must be permit or forbid, got {effect!r}",
            feature="effect",
        )

    annotations = policy.get("annotations") or {}
    if not isinstance(annotations, dict):
        raise InvalidCedarSyntax("annotations must be an object", feature="annotations")

    rule: dict[str, Any] = {}

    for key in ("id", "description", "message", "recommendation", "severity", "iso_control"):
        if key in annotations:
            rule[key] = annotations[key]

    advice = annotations.get("advice")
    if effect == "forbid":
        rule["action"] = ADVICE_ACTION_MAP.get(advice, "block")
    else:
        rule["action"] = ADVICE_ACTION_MAP.get(advice, "audit")

    compliance = annotations.get("compliance")
    if compliance:
        if isinstance(compliance, str):
            rule["frameworks"] = [f.strip() for f in compliance.split(",") if f.strip()]
        elif isinstance(compliance, list):
            rule["frameworks"] = list(compliance)

    _apply_principal(policy.get("principal") or {}, rule)
    _apply_action(policy.get("action") or {}, rule)

    for cond in policy.get("conditions") or []:
        _apply_condition(cond, rule)

    if "match_tool" not in rule:
        rule["match_tool"] = "*"

    return rule


def _apply_principal(principal: dict[str, Any], rule: dict[str, Any]) -> None:
    if not principal:
        return
    op = principal.get("op")
    if op == "==":
        entity = principal.get("entity") or {}
        etype = entity.get("type", "")
        if etype in ("User", "Agent"):
            raise UnsupportedCedarFeature(
                "principal equality on User is not supported. Packs are workspace-scoped.",
                feature="principal_specific_user",
                snippet=str(principal)[:200],
                hint="Use `principal is <PersonaType>` for role-based rules.",
            )
    if op == "is":
        etype = principal.get("entity_type") or principal.get("type", "")
        persona = PERSONA_TYPE_MAP.get(etype)
        if persona:
            rule["persona_affinity"] = [persona]
        else:
            raise UnsupportedCedarFeature(
                f"principal is {etype!r} does not map to a known Guard persona.",
                feature="unknown_principal_type",
                snippet=str(principal)[:200],
                hint=f"Supported persona types: {sorted(PERSONA_TYPE_MAP.keys())}",
            )
    if op == "in":
        raise UnsupportedCedarFeature(
            "principal in Group not supported.",
            feature="principal_in_hierarchy",
            snippet=str(principal)[:200],
            hint="Use `principal is <PersonaType>` for role-based rules.",
        )


def _apply_action(action: dict[str, Any], rule: dict[str, Any]) -> None:
    if not action:
        return
    op = action.get("op")
    if op == "==":
        entity = action.get("entity") or {}
        tool_name = entity.get("id")
        if not tool_name:
            raise InvalidCedarSyntax(
                "action equality expects an entity with an id",
                feature="action_equals",
            )
        rule["match_tool"] = tool_name
    elif op == "in":
        entities = action.get("entities")
        if entities is None:
            raise UnsupportedCedarFeature(
                "action in ActionGroup not supported for MVP.",
                feature="action_group",
                snippet=str(action)[:200],
                hint="Use action in [Action::X, Action::Y] (explicit list) instead.",
            )
        tools = []
        for e in entities:
            tid = (e or {}).get("id")
            if not tid:
                raise InvalidCedarSyntax(
                    "action in list requires each entity to have an id",
                    feature="action_in_list",
                )
            tools.append(tid)
        rule["match_tool"] = ",".join(tools)


def _apply_condition(cond: dict[str, Any], rule: dict[str, Any]) -> None:
    kind = cond.get("kind")
    body = cond.get("body")
    if kind == "unless":
        raise UnsupportedCedarFeature(
            "unless clauses not supported for MVP.",
            feature="unless_clause",
            hint="Express negation inside a when using !.",
        )
    if kind != "when":
        raise InvalidCedarSyntax(
            f"Unknown condition kind {kind!r}",
            feature="condition_kind",
        )
    if not isinstance(body, dict):
        raise InvalidCedarSyntax("condition body must be an object", feature="condition_body")
    _extract_matchers_from_expr(body, rule)


def _extract_matchers_from_expr(expr: dict[str, Any], rule: dict[str, Any]) -> None:
    op_key = next(iter(expr.keys()), None)
    if op_key is None:
        return
    if op_key == "&&":
        for arg in expr[op_key] if isinstance(expr[op_key], list) else []:
            _extract_matchers_from_expr(arg, rule)
        return
    if op_key == "||":
        raise UnsupportedCedarFeature(
            "or operator in conditions not supported for MVP.",
            feature="or_operator",
            snippet=str(expr)[:200],
            hint="Split into multiple separate permit or forbid policies.",
        )
    if op_key == "matches":
        _apply_matches(expr[op_key], rule)
        return
    if op_key in ("==", "!=", "<", "<=", ">", ">="):
        _apply_comparison(op_key, expr[op_key], rule)
        return
    raise UnsupportedCedarFeature(
        f"Cedar operator {op_key!r} not supported for MVP.",
        feature=f"operator_{op_key}",
        snippet=str(expr)[:200],
        hint="Supported: comparisons, matches, and-operator.",
    )


def _apply_matches(args: list[Any], rule: dict[str, Any]) -> None:
    if not isinstance(args, list) or len(args) != 2:
        raise InvalidCedarSyntax("matches expects two arguments", feature="matches_arity")
    left, right = args
    attr = _context_attribute_name(left)
    pattern = _string_value(right)
    if attr == "prompt":
        rule["match_pattern"] = pattern
    elif attr == "path":
        rule["match_path_pattern"] = pattern
    elif attr == "model":
        rule["match_model"] = pattern
    else:
        rule["match_pattern"] = pattern


def _apply_comparison(op: str, args: list[Any], rule: dict[str, Any]) -> None:
    if not isinstance(args, list) or len(args) != 2:
        raise InvalidCedarSyntax(f"{op} expects two arguments", feature=f"op_{op}_arity")
    left, right = args
    attr = _context_attribute_name(left)
    if attr == "tokens_before" and op == ">":
        rule["match_tokens_before_gt"] = _int_value(right)
        return
    if op == "==":
        value = _string_value(right)
        if attr == "risk_tier":
            rule["match_agent_risk_tier"] = value
            return
        if attr == "ai_tool":
            rule["match_ai_tool"] = value
            return
        if attr == "mcp_server":
            rule["match_mcp_server"] = value
            return
        if attr == "model":
            rule["match_model"] = value
            return
    raise UnsupportedCedarFeature(
        f"Comparison on context.{attr} with {op} not supported.",
        feature=f"comparison_{attr}_{op}",
        hint="Supported context attributes: prompt, path, tokens_before, risk_tier, ai_tool, mcp_server, model.",
    )


def _context_attribute_name(node: Any) -> str:
    if not isinstance(node, dict):
        raise InvalidCedarSyntax("Expected an attribute access expression", snippet=str(node)[:200])
    dot = node.get(".")
    if isinstance(dot, dict):
        left = dot.get("left") or {}
        if isinstance(left, dict) and left.get("Var") == "context":
            attr = dot.get("attr")
            if isinstance(attr, str):
                return attr
    raise UnsupportedCedarFeature(
        "Only context.attribute access is supported on the left side.",
        feature="attribute_access",
        snippet=str(node)[:200],
        hint="Use context.attr == value style expressions.",
    )


def _string_value(node: Any) -> str:
    if isinstance(node, dict):
        if "Value" in node and isinstance(node["Value"], str):
            return node["Value"]
        if "Literal" in node and isinstance(node["Literal"], str):
            return node["Literal"]
    if isinstance(node, str):
        return node
    raise InvalidCedarSyntax(
        f"Expected a string value, got {type(node).__name__}",
        snippet=str(node)[:200],
    )


def _int_value(node: Any) -> int:
    if isinstance(node, dict):
        v = node.get("Value")
        if isinstance(v, int):
            return v
        if isinstance(v, str) and v.isdigit():
            return int(v)
    if isinstance(node, int):
        return node
    raise InvalidCedarSyntax(
        f"Expected an integer value, got {type(node).__name__}",
        snippet=str(node)[:200],
    )


def cedar_json_bundle_to_pack(
    policies: list[dict[str, Any]],
    pack_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Convert a list of Cedar JSON policies to a full Guard pack."""
    pack: dict[str, Any] = {
        "slug": pack_metadata.get("slug") or "imported-cedar-pack",
        "name": pack_metadata.get("name") or "Imported Cedar Pack",
        "version": pack_metadata.get("version") or "1.0.0",
        "tier": pack_metadata.get("tier") or "paid",
        "description": pack_metadata.get("description") or "Imported from Cedar policies.",
        "rules": [],
        "_rejections": [],
    }
    for idx, policy in enumerate(policies):
        try:
            pack["rules"].append(cedar_json_to_rule(policy))
        except (InvalidCedarSyntax, UnsupportedCedarFeature) as e:
            pack["_rejections"].append({"index": idx, "error": e.to_dict()})
    return pack
