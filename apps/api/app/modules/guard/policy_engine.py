"""
Policy engine — compute_policy().

Resolves the active rule set for a workspace+persona by:
  1. Collecting rules from all installed skill packs (latest version unless pinned)
  2. Applying workspace overrides (disable or change action)
  3. Caching the result in guard_policy_cache
  4. Returning the cached payload on subsequent calls until invalidated

Cache invalidation: call invalidate_policy_cache(db, workspace_id) whenever
  - a skill pack is installed or removed
  - a GuardRuleOverride is created, updated, or deleted
  - the workspace persona changes
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.guard.models import (
    GuardPolicyCache,
    GuardRuleOverride,
    SkillPack,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.enforcement import rule_personas

PERSONAS = ["agent", "proxy"]

ACTION_RESTRICTIVENESS = {
    "allow": 0,
    "audit": 1,
    "inject": 2,
    "warn": 3,
    "approval": 4,
    "block": 5,
}
VALID_ACTIONS = frozenset({"audit", "inject", "warn", "approval", "block"})


def _skill_pack_version_key(version: str) -> tuple[tuple[int, int | str], ...]:
    """Sort dotted versions numerically while retaining deterministic fallback."""
    parts: list[tuple[int, int | str]] = []
    for part in version.split("."):
        parts.append((1, int(part)) if part.isdigit() else (0, part))
    return tuple(parts)


def is_action_relaxing(base_action: str | None, override_action: str | None) -> bool:
    """Return whether a known override action weakens a known base action."""
    if not override_action or override_action == base_action:
        return False
    if base_action not in ACTION_RESTRICTIVENESS or override_action not in ACTION_RESTRICTIVENESS:
        return True
    return ACTION_RESTRICTIVENESS[override_action] < ACTION_RESTRICTIVENESS[base_action]


def is_exception_active(
    override: GuardRuleOverride,
    base_action: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Security-relaxing overrides are active only with reason + future expiry."""
    relaxing = bool(override.disabled or is_action_relaxing(base_action, override.action))
    if not relaxing:
        return False
    current_time = now or datetime.now(timezone.utc)
    return bool(
        override.reason
        and override.reason.strip()
        and override.expires_at is not None
        and override.expires_at > current_time
    )


# ── Public API ────────────────────────────────────────────────────────────────

def compute_policy(db: Session, workspace_id: uuid.UUID, persona: str) -> list[dict]:
    """Return active rules for workspace+persona. Served from cache when fresh."""
    cached = db.get(GuardPolicyCache, (workspace_id, persona))
    if cached:
        now = datetime.now(timezone.utc)
        crossed_expiry = (
            db.query(GuardRuleOverride)
            .filter(
                GuardRuleOverride.workspace_id == workspace_id,
                GuardRuleOverride.expires_at.isnot(None),
                GuardRuleOverride.expires_at <= now,
                GuardRuleOverride.expires_at > cached.computed_at,
            )
            .first()
        )
        if not crossed_expiry:
            return cached.payload
        db.delete(cached)
        db.flush()

    rules = _build_rules(db, workspace_id, persona)
    _write_cache(db, workspace_id, persona, rules)
    return rules


def invalidate_policy_cache(db: Session, workspace_id: uuid.UUID) -> None:
    """Wipe all cached personas for a workspace. Call after any policy change."""
    db.query(GuardPolicyCache).filter(
        GuardPolicyCache.workspace_id == workspace_id
    ).delete(synchronize_session="fetch")
    # Also expire the session identity map so any cached ORM instances are
    # rediscovered from the DB on the next compute_policy() call. Without this,
    # db.get(GuardPolicyCache, ...) in the same session returns a stale row.
    db.expire_all()
    # Push invalidation to any connected conduct-daemon instances
    try:
        from app.modules.guard.routers.ws import publish_policy_invalidated
        publish_policy_invalidated(workspace_id)
    except Exception:
        pass  # Redis unavailable must never block a policy write


# ── Internal ──────────────────────────────────────────────────────────────────

def _build_rules(db: Session, workspace_id: uuid.UUID, persona: str) -> list[dict]:
    # 1. collect rules from installed packs, filtered by persona
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == workspace_id)
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )

    rules: dict[str, dict] = {}
    for wp in installed:
        pack = _get_pack(db, wp.pack_slug, wp.pinned_version)
        if not pack:
            continue
        for rule in pack.rules:
            if persona not in rule_personas(rule):
                continue
            body = dict(rule)
            # #1048: stamp source_pack so downstream (sync response, audit,
            # debugging) can trace 'which pack put this rule into my cache'.
            body["source_pack"] = wp.pack_slug
            rules[rule["id"]] = body

    # 1b. merge workspace custom rules on top (workspace-defined wins on rule_id collision)
    customs = (
        db.query(WorkspaceCustomRule)
        .filter(
            WorkspaceCustomRule.workspace_id == workspace_id,
            WorkspaceCustomRule.enabled.is_(True),
            (WorkspaceCustomRule.persona == persona) | (WorkspaceCustomRule.persona.is_(None)),
        )
        .all()
    )
    for c in customs:
        body = dict(c.body or {})
        body.setdefault("id", c.rule_id)
        affinity = body.get("persona_affinity", PERSONAS)
        if persona not in affinity:
            continue
        rules[c.rule_id] = body

    # 2. apply workspace overrides
    overrides = (
        db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id == workspace_id)
        .all()
    )
    now = datetime.now(timezone.utc)
    for o in overrides:
        if o.rule_id not in rules:
            continue
        base_action = rules[o.rule_id].get("action", "block")
        relaxing_action = is_action_relaxing(base_action, o.action)
        requires_expiry = bool(o.disabled or relaxing_action)
        exception_active = is_exception_active(o, base_action, now=now)

        if o.disabled and exception_active:
            del rules[o.rule_id]
        else:
            if (
                o.action in VALID_ACTIONS
                and (not requires_expiry or exception_active)
            ):
                rules[o.rule_id]["action"] = o.action
            if o.custom_message:
                rules[o.rule_id]["message"] = o.custom_message

    # #1141: retire standalone action:inject → audit + inject_guidance=true.
    # Decouples decision (block/warn/audit/approval) from side-effect (nudge model).
    for rule in rules.values():
        if rule.get("action") == "inject":
            rule["action"] = "audit"
            rule["inject_guidance"] = True

    return list(rules.values())


def _get_pack(db: Session, slug: str, pinned_version: str | None) -> SkillPack | None:
    if pinned_version:
        return db.get(SkillPack, (slug, pinned_version))
    packs = (
        db.query(SkillPack)
        .filter(SkillPack.slug == slug)
        .all()
    )
    return max(packs, key=lambda pack: _skill_pack_version_key(pack.version), default=None)


def _write_cache(
    db: Session,
    workspace_id: uuid.UUID,
    persona: str,
    rules: list[dict],
) -> None:
    version_hash = hashlib.sha256(
        json.dumps(rules, sort_keys=True).encode()
    ).hexdigest()[:16]

    existing = db.get(GuardPolicyCache, (workspace_id, persona))
    if existing:
        existing.payload = rules
        existing.version_hash = version_hash
        existing.computed_at = datetime.now(timezone.utc)
    else:
        db.add(GuardPolicyCache(
            workspace_id=workspace_id,
            persona=persona,
            payload=rules,
            version_hash=version_hash,
            computed_at=datetime.now(timezone.utc),
        ))



# ── Canonical workspace resolution ────────────────────────────────────────────
# Shared by proxy.py and guard_block.py — lives here to avoid cross-layer imports.

from functools import lru_cache as _lru_cache
from app.core.database import SessionLocal as _SessionLocal
from app.models.workspace import Workspace as _Workspace


def _resolve_canonical_workspace(db: Session, workspace_id: str) -> str:
    """Return oldest workspace under the same owner. Falls back to workspace_id."""
    try:
        ws = db.query(_Workspace).filter(_Workspace.id == uuid.UUID(workspace_id)).first()
    except Exception:
        return workspace_id
    if ws and ws.owner_id:
        canonical = (
            db.query(_Workspace)
            .filter(_Workspace.owner_id == ws.owner_id)
            .order_by(_Workspace.created_at.asc())
            .first()
        )
        if canonical:
            return str(canonical.id)
    return workspace_id


@_lru_cache(maxsize=256)
def canonical_workspace_id(workspace_id: str) -> str:
    """Cached version — one DB round-trip per unique workspace_id per worker."""
    db = _SessionLocal()
    try:
        return _resolve_canonical_workspace(db, workspace_id)
    finally:
        db.close()
