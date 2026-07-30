"""Generated workspace enforcement coverage from resolved policy metadata."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.modules.guard.enforcement import (
    conservative_custom_enforcement,
    rule_personas,
    validate_enforcement_metadata,
)
from app.modules.guard.models import (
    GuardRuleOverride,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import (
    VALID_ACTIONS,
    _get_pack,
    is_action_relaxing,
    is_exception_active,
)


def workspace_coverage_matrix(db: Session, workspace_id: uuid.UUID) -> list[dict[str, Any]]:
    """Return the resolved rule matrix for installed/pinned packs and custom rules."""
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == workspace_id)
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    resolved: dict[str, dict[str, Any]] = {}
    for installation in installed:
        pack = _get_pack(db, installation.pack_slug, installation.pinned_version)
        if not pack:
            continue
        for source_rule in pack.rules or []:
            rule = dict(source_rule)
            rule["_pack_slug"] = pack.slug
            rule["_pack_version"] = pack.version
            rule["_builtin"] = True
            resolved[rule["id"]] = rule

    customs = (
        db.query(WorkspaceCustomRule)
        .filter(WorkspaceCustomRule.workspace_id == workspace_id)
        .all()
    )
    for custom in customs:
        body = dict(custom.body or {})
        body.setdefault("id", custom.rule_id)
        body["_pack_slug"] = None
        body["_pack_version"] = None
        body["_builtin"] = False
        body["_custom_enabled"] = bool(custom.enabled)
        body["_custom_persona"] = custom.persona
        if custom.persona and "persona" not in body and "persona_affinity" not in body:
            body["persona"] = custom.persona
        resolved[custom.rule_id] = body

    overrides = {
        override.rule_id: override
        for override in db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id == workspace_id)
        .all()
    }
    now = datetime.now(timezone.utc)
    matrix: list[dict[str, Any]] = []
    for rule_id, rule in resolved.items():
        metadata = rule.get("enforcement")
        if metadata is None:
            if rule.get("_builtin"):
                validate_enforcement_metadata(rule)
            metadata = conservative_custom_enforcement(rule)
        else:
            validate_enforcement_metadata(rule)

        base_action = rule.get("action", "audit")
        effective_action = base_action
        enabled = rule.get("_custom_enabled", True)
        override = overrides.get(rule_id)
        relaxing = bool(
            override
            and (override.disabled or is_action_relaxing(base_action, override.action))
        )
        active_exception = bool(
            override and is_exception_active(override, base_action, now=now)
        )
        expired_exception = bool(
            relaxing
            and override
            and override.expires_at is not None
            and override.expires_at <= now
        )
        if override:
            if override.disabled and active_exception:
                enabled = False
            if override.action in VALID_ACTIONS and (not relaxing or active_exception):
                effective_action = override.action

        personas = sorted(rule_personas(rule))
        if not rule.get("_builtin") and rule.get("_custom_persona"):
            personas = [rule["_custom_persona"]]
        matrix.append({
            "rule_id": rule_id,
            "name": rule.get("name") or rule.get("description") or rule_id,
            "pack": rule.get("_pack_slug"),
            "pack_version": rule.get("_pack_version"),
            "builtin": bool(rule.get("_builtin")),
            "personas": personas,
            "action": effective_action,
            "base_action": base_action,
            "enabled": enabled,
            "proxy": metadata["proxy"],
            "hook": metadata["hook"],
            "mcp": metadata["mcp"],
            "runtime": metadata["runtime"],
            "guarantee": metadata["guarantee"],
            "requires": list(metadata["requires"]),
            "known_limitations": list(metadata["known_limitations"]),
            "enforcement_version": metadata["version"],
            "exception_reason": override.reason if override and relaxing else None,
            "exception_expires_at": override.expires_at if override and relaxing else None,
            "exception_active": active_exception,
            "exception_expired": expired_exception,
        })

    return sorted(
        matrix,
        key=lambda item: (item["pack"] or "~custom", item["pack_version"] or "", item["rule_id"]),
    )
