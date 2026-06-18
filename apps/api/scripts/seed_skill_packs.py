"""
Seed skill packs from existing builtin_policies.yaml and compliance.py data.

Steps:
  1. Seed skill_packs table with conduct-base + compliance packs
  2. Auto-install conduct-base for every workspace that has guard_config
  3. Auto-install compliance packs for workspaces that have pack_id rows in guard_policies
  4. Migrate disabled builtin rules to guard_rule_overrides

Run AFTER alembic upgrade 0017. Does NOT drop guard_policies — that's a
separate step once this is verified in production.

Usage:
  python apps/api/scripts/seed_skill_packs.py
  python apps/api/scripts/seed_skill_packs.py --dry-run
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
SKILL_PACKS_DIR = APPS_API / "app/modules/guard/skill_packs"
sys.path.insert(0, str(APPS_API))

_env = APPS_API / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.modules.guard.models import (
    GuardConfig, GuardPolicy,
    SkillPack, WorkspaceSkillPack, GuardRuleOverride,
)

NOW = datetime.now(timezone.utc)

# ── Pack definitions (loaded from JSON files) ─────────────────────────────────

PACK_SLUGS = ["conduct-base", "conduct-owasp", "conduct-soc2", "conduct-hipaa", "conduct-pci-dss"]


def _load_pack(slug: str) -> dict:
    return json.loads((SKILL_PACKS_DIR / f"{slug}.json").read_text())

# legacy pack_id → new slug
LEGACY_PACK_MAP = {
    "owasp_top10":      "conduct-owasp",
    "soc2":             "conduct-soc2",
    "hipaa":            "conduct-hipaa",
    "pci_dss":          "conduct-pci-dss",
    "startup_baseline": "conduct-base",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(rules: list[dict]) -> str:
    return hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:16]


def _upsert_pack(db: Session, slug: str, dry_run: bool) -> None:
    pack = _load_pack(slug)
    version = pack["version"]
    existing = db.get(SkillPack, (slug, version))
    if existing:
        print(f"  skill_pack {slug} {version} already exists — skipping")
        return
    if not dry_run:
        db.add(SkillPack(
            slug=slug, version=version,
            name=pack["name"], description=pack["description"], tier=pack["tier"],
            rules=pack["rules"], published_at=NOW, created_at=NOW,
        ))
    print(f"  {'[dry]' if dry_run else ''} seeded {slug} v{version} ({len(pack['rules'])} rules, tier={pack['tier']})")


def _auto_install(db: Session, workspace_id, slug: str, dry_run: bool) -> None:
    existing = db.get(WorkspaceSkillPack, (workspace_id, slug))
    if existing:
        return
    if not dry_run:
        db.add(WorkspaceSkillPack(
            workspace_id=workspace_id,
            pack_slug=slug,
            pinned_version=None,
            installed_by="system:migration",
            installed_at=NOW,
        ))


# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool) -> None:
    db: Session = SessionLocal()
    try:
        # 1. Seed skill_packs
        print("\n── Seeding skill_packs ──")
        for slug in PACK_SLUGS:
            _upsert_pack(db, slug, dry_run)
        if not dry_run:
            db.flush()

        # 2. Auto-install conduct-base for every workspace with a guard_config
        print("\n── Installing conduct-base for all workspaces ──")
        configs = db.query(GuardConfig).all()
        for cfg in configs:
            _auto_install(db, cfg.workspace_id, "conduct-base", dry_run)
            if not dry_run:
                pass  # will flush below
        print(f"  {'[dry]' if dry_run else ''} {len(configs)} workspaces → conduct-base")

        # 3. Auto-install compliance packs where pack_id rows exist
        print("\n── Migrating legacy compliance pack installs ──")
        legacy_rows = (
            db.query(GuardPolicy.workspace_id, GuardPolicy.pack_id)
            .filter(GuardPolicy.pack_id.isnot(None))
            .distinct()
            .all()
        )
        migrated = 0
        for ws_id, legacy_pack_id in legacy_rows:
            new_slug = LEGACY_PACK_MAP.get(legacy_pack_id)
            if not new_slug:
                print(f"  WARNING: unknown legacy pack_id '{legacy_pack_id}' — skipped")
                continue
            _auto_install(db, ws_id, new_slug, dry_run)
            migrated += 1
        print(f"  {'[dry]' if dry_run else ''} {migrated} legacy pack installs migrated")

        # 4. Migrate disabled builtin rules → guard_rule_overrides
        print("\n── Migrating disabled builtin rules → guard_rule_overrides ──")
        disabled = (
            db.query(GuardPolicy)
            .filter(GuardPolicy.builtin == True, GuardPolicy.enabled == False)
            .all()
        )
        for p in disabled:
            existing = db.get(GuardRuleOverride, (p.workspace_id, p.rule_id))
            if existing:
                continue
            if not dry_run:
                db.add(GuardRuleOverride(
                    workspace_id=p.workspace_id,
                    rule_id=p.rule_id,
                    disabled=True,
                    overridden_by="system:migration",
                    overridden_at=NOW,
                ))
        print(f"  {'[dry]' if dry_run else ''} {len(disabled)} disabled builtin rules → overrides")

        if not dry_run:
            db.commit()
            print("\n✓ Done. guard_policies table preserved — verify new tables before dropping.")
        else:
            db.rollback()
            print("\n[dry-run] No changes committed.")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
