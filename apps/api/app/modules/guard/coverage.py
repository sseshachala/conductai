"""Generated workspace enforcement coverage from resolved policy metadata."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

from app.modules.guard.enforcement import (
    GATES,
    EnforcementMetadataError,
    conservative_custom_enforcement,
    derive_gates,
    derive_surface_status,
    rule_personas,
    validate_enforcement_metadata,
)
from app.modules.guard.models import (
    GuardRuleOverride,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.pep_registry import all_surfaces
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
        # Validate what we have; fall back to the conservative contract when
        # metadata is missing. A single stale rule must not crash the whole
        # coverage endpoint — log + skip it instead so the matrix still
        # renders for every other rule in the workspace.
        try:
            if metadata is None:
                metadata = conservative_custom_enforcement(rule)
            else:
                validate_enforcement_metadata(rule)
        except EnforcementMetadataError as exc:
            log.warning(
                "guard.coverage.rule_metadata_invalid",
                rule_id=rule_id,
                pack=rule.get("_pack_slug"),
                pack_version=rule.get("_pack_version"),
                builtin=bool(rule.get("_builtin")),
                error=str(exc),
            )
            continue

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

        # #1751 PR 4: log divergence between hand-authored enforcement.<surface>
        # and derive_surface_status(rule, surface). Telemetry for #1750 Phase D
        # cleanup — every 'not_supported' claim that's actually 'hard' (or vice
        # versa) points at a rule whose hand-authored metadata is stale.
        for _surface in ("proxy", "hook", "mcp", "runtime"):
            _authored = metadata.get(_surface)
            _derived = derive_surface_status(rule, _surface)
            # 'conditional' and 'advisory' are deploy-caveat statuses derived
            # doesn't model yet; only flag hard↔not_supported flips.
            if _authored in ("hard", "not_supported") and _authored != _derived:
                log.warning(
                    "guard.coverage.status_divergence",
                    rule_id=rule_id,
                    pack=rule.get("_pack_slug"),
                    surface=_surface,
                    authored=_authored,
                    derived=_derived,
                    note="#1750 Phase D: authored value is stale; derived is authoritative",
                )

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
            # #1755 Slice 2 (real PR 5) — derived counterparts for divergence UI.
            "derived_proxy": derive_surface_status(rule, "proxy"),
            "derived_hook": derive_surface_status(rule, "hook"),
            "derived_mcp": derive_surface_status(rule, "mcp"),
            "derived_runtime": derive_surface_status(rule, "runtime"),
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


def pack_coverage_matrix(db: Session, pack_slug: str) -> dict[str, Any]:
    """#1751 PR 3 — return per-surface × per-gate rule counts for a pack.

    Answers the Policies UI question "does this pack cover response-gate
    leakage on the proxy?" in one call.

    Shape::
        {
            "pack": "conduct-hipaa",
            "version": "1.4.2",
            "total_rules": 42,
            "by_surface": {
                "mcp":     {"hard": 27, "not_supported": 15},
                "proxy":   {"hard": 12, "not_supported": 30},
                "runtime": {"hard": 27, "not_supported": 15},
                "hook":    {"hard": 27, "not_supported": 15},
            },
            "by_gate": {"action": 30, "prompt": 10, "response": 2},
        }

    Missing pack → ``{"pack": pack_slug, "version": None, "total_rules": 0,
    "by_surface": {surface: {"hard": 0, "not_supported": 0} ...},
    "by_gate": {gate: 0 ...}}`` so UI callers can render an empty state
    without a null check.
    """
    surfaces = all_surfaces()
    empty_by_surface = {s: {"hard": 0, "not_supported": 0} for s in surfaces}
    empty_by_gate = {g: 0 for g in GATES}

    pack = _get_pack(db, pack_slug, pinned_version=None)
    if pack is None:
        return {
            "pack": pack_slug,
            "version": None,
            "total_rules": 0,
            "by_surface": empty_by_surface,
            "by_gate": empty_by_gate,
        }

    by_surface = {s: {"hard": 0, "not_supported": 0} for s in surfaces}
    by_gate = {g: 0 for g in GATES}
    total = 0
    for rule in pack.rules or []:
        total += 1
        for gate in derive_gates(rule):
            if gate in by_gate:
                by_gate[gate] += 1
        for surface in surfaces:
            status = derive_surface_status(rule, surface)
            key = status if status in by_surface[surface] else "not_supported"
            by_surface[surface][key] += 1

    return {
        "pack": pack_slug,
        "version": pack.version,
        "total_rules": total,
        "by_surface": by_surface,
        "by_gate": by_gate,
    }
