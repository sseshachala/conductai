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
    WorkspaceSkillPack,
)

PERSONAS = ["conservative", "standard", "developer"]


# ── Public API ────────────────────────────────────────────────────────────────

def compute_policy(db: Session, workspace_id: uuid.UUID, persona: str) -> list[dict]:
    """Return active rules for workspace+persona. Served from cache when fresh."""
    cached = db.get(GuardPolicyCache, (workspace_id, persona))
    if cached:
        return cached.payload

    rules = _build_rules(db, workspace_id, persona)
    _write_cache(db, workspace_id, persona, rules)
    return rules


def invalidate_policy_cache(db: Session, workspace_id: uuid.UUID) -> None:
    """Wipe all cached personas for a workspace. Call after any policy change."""
    db.query(GuardPolicyCache).filter(
        GuardPolicyCache.workspace_id == workspace_id
    ).delete(synchronize_session=False)
    # Push invalidation to any connected conduct-daemon instances
    try:
        from app.modules.guard.routers.ws import publish_policy_invalidated
        publish_policy_invalidated(workspace_id)
    except Exception:
        pass  # Redis unavailable must never block a policy write


# ── Internal ──────────────────────────────────────────────────────────────────

def _build_rules(db: Session, workspace_id: uuid.UUID, persona: str) -> list[dict]:
    # 1. collect rules from installed packs, in install order
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
            affinity = rule.get("persona_affinity", PERSONAS)
            if persona not in affinity:
                continue
            rules[rule["id"]] = dict(rule)

    # 2. apply workspace overrides
    overrides = (
        db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id == workspace_id)
        .all()
    )
    for o in overrides:
        if o.rule_id not in rules:
            continue
        if o.disabled:
            del rules[o.rule_id]
        else:
            if o.action:
                rules[o.rule_id]["action"] = o.action
            if o.custom_message:
                rules[o.rule_id]["message"] = o.custom_message

    return list(rules.values())


def _get_pack(db: Session, slug: str, pinned_version: str | None) -> SkillPack | None:
    if pinned_version:
        return db.get(SkillPack, (slug, pinned_version))
    # latest = highest version string (semver sort via PG string sort is good enough for x.y.z)
    return (
        db.query(SkillPack)
        .filter(SkillPack.slug == slug)
        .order_by(SkillPack.version.desc())
        .first()
    )


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
