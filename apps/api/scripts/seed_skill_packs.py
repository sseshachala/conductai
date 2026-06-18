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

from sqlalchemy import text as _text
from app.core.database import engine

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

# ── Main (raw SQL — avoids ORM relationship resolution issues) ────────────────

def run(dry_run: bool) -> None:
    with engine.connect() as conn:
        with conn.begin():
            # 1. Seed skill_packs
            print("\n── Seeding skill_packs ──")
            for slug in PACK_SLUGS:
                pack = _load_pack(slug)
                version = pack["version"]
                exists = conn.execute(_text(
                    "SELECT 1 FROM skill_packs WHERE slug=:s AND version=:v"
                ), {"s": slug, "v": version}).fetchone()
                if exists:
                    print(f"  skill_pack {slug} {version} already exists — skipping")
                    continue
                if not dry_run:
                    conn.execute(_text("""
                        INSERT INTO skill_packs (slug, version, name, description, tier, rules, published_at, created_at)
                        VALUES (:slug, :version, :name, :desc, :tier, CAST(:rules AS jsonb), :now, :now)
                        ON CONFLICT (slug, version) DO NOTHING
                    """), {
                        "slug": slug, "version": version,
                        "name": pack["name"], "desc": pack.get("description", ""),
                        "tier": pack["tier"], "rules": json.dumps(pack["rules"]),
                        "now": NOW,
                    })
                print(f"  {'[dry]' if dry_run else ''} seeded {slug} v{version} ({len(pack['rules'])} rules, tier={pack['tier']})")

            # 2. Auto-install conduct-base for every workspace with a guard_config
            print("\n── Installing conduct-base for all workspaces ──")
            configs = conn.execute(_text("SELECT workspace_id FROM guard_config")).fetchall()
            for (ws_id,) in configs:
                if not dry_run:
                    conn.execute(_text("""
                        INSERT INTO workspace_skill_packs (workspace_id, pack_slug, installed_by, installed_at)
                        VALUES (:ws, 'conduct-base', 'system:migration', :now)
                        ON CONFLICT (workspace_id, pack_slug) DO NOTHING
                    """), {"ws": ws_id, "now": NOW})
            print(f"  {'[dry]' if dry_run else ''} {len(configs)} workspaces → conduct-base")

            # 3. Migrate legacy compliance pack installs
            print("\n── Migrating legacy compliance pack installs ──")
            legacy_rows = conn.execute(_text(
                "SELECT DISTINCT workspace_id, pack_id FROM guard_policies WHERE pack_id IS NOT NULL"
            )).fetchall()
            migrated = 0
            for ws_id, legacy_pack_id in legacy_rows:
                new_slug = LEGACY_PACK_MAP.get(legacy_pack_id)
                if not new_slug:
                    print(f"  WARNING: unknown legacy pack_id '{legacy_pack_id}' — skipped")
                    continue
                if not dry_run:
                    conn.execute(_text("""
                        INSERT INTO workspace_skill_packs (workspace_id, pack_slug, installed_by, installed_at)
                        VALUES (:ws, :slug, 'system:migration', :now)
                        ON CONFLICT (workspace_id, pack_slug) DO NOTHING
                    """), {"ws": ws_id, "slug": new_slug, "now": NOW})
                migrated += 1
            print(f"  {'[dry]' if dry_run else ''} {migrated} legacy pack installs migrated")

            # 4. Migrate disabled builtin rules → guard_rule_overrides
            print("\n── Migrating disabled builtin rules → guard_rule_overrides ──")
            disabled = conn.execute(_text(
                "SELECT workspace_id, rule_id FROM guard_policies WHERE builtin=true AND enabled=false"
            )).fetchall()
            for ws_id, rule_id in disabled:
                if not dry_run:
                    conn.execute(_text("""
                        INSERT INTO guard_rule_overrides (workspace_id, rule_id, disabled, overridden_by, overridden_at)
                        VALUES (:ws, :rid, true, 'system:migration', :now)
                        ON CONFLICT (workspace_id, rule_id) DO NOTHING
                    """), {"ws": ws_id, "rid": rule_id, "now": NOW})
            print(f"  {'[dry]' if dry_run else ''} {len(disabled)} disabled builtin rules → overrides")

            if dry_run:
                conn.execute(_text("ROLLBACK"))
                print("\n[dry-run] No changes committed.")
            else:
                print("\n✓ Done. guard_policies table preserved — verify new tables before dropping.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    run(dry_run=args.dry_run)
