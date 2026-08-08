"""
Seed skill packs from existing builtin_policies.yaml and compliance.py data.

Steps:
  1. Seed skill_packs table with conduct-base + compliance packs
  2. Auto-install conduct-base for every workspace that has guard_config

Idempotent — runs after migrations. Loads pack JSON files into skill_packs
and auto-installs conduct-base for every workspace that has guard_config.

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
from app.modules.guard.enforcement import validate_pack

NOW = datetime.now(timezone.utc)

# ── Pack definitions (loaded from JSON files) ─────────────────────────────────

PACK_SLUGS = ["conduct-base", "conduct-owasp", "conduct-soc2", "conduct-hipaa", "conduct-pci-dss", "conduct-eu-ai-act", "conduct-nist-ai-rmf", "conduct-iso-42001", "conduct-irs-1075", "surface-aware", "meridian-dispatch"]


def _load_pack(slug: str) -> dict:
    path = SKILL_PACKS_DIR / f"{slug}.json"
    pack = json.loads(path.read_text())
    validate_pack(pack, source=str(path))
    return pack

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

def run(dry_run: bool, force: bool = False) -> None:
    with engine.connect() as conn:
        with conn.begin():
            # 1. Seed skill_packs
            print("\n── Seeding skill_packs ──")
            for slug in PACK_SLUGS:
                pack = _load_pack(slug)
                version = pack["version"]
                existing = conn.execute(_text(
                    "SELECT rules FROM skill_packs WHERE slug=:s AND version=:v"
                ), {"s": slug, "v": version}).fetchone()
                has_current_contract = bool(
                    existing
                    and existing[0]
                    and all(
                        isinstance(rule.get("enforcement"), dict)
                        and rule["enforcement"].get("version") == 1
                        for rule in (existing[0] or [])
                    )
                )
                if existing and has_current_contract and not force:
                    print(f"  skill_pack {slug} {version} already exists — skipping")
                    continue
                if not dry_run:
                    conn.execute(_text("""
                        INSERT INTO skill_packs (slug, version, name, description, tier, rules, published_at, created_at)
                        VALUES (:slug, :version, :name, :desc, :tier, CAST(:rules AS jsonb), :now, :now)
                        ON CONFLICT (slug, version) DO UPDATE
                          SET name=EXCLUDED.name, description=EXCLUDED.description,
                              tier=EXCLUDED.tier, rules=EXCLUDED.rules
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

            if dry_run:
                conn.execute(_text("ROLLBACK"))
                print("\n[dry-run] No changes committed.")
            else:
                print("\n✓ Done.")



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing pack versions")
    args = parser.parse_args()
    run(dry_run=args.dry_run, force=args.force)
