"""Validate every skill_pack JSON — exit nonzero on any contract failure.

Run in CI + as a local pre-commit hook so a broken pack never reaches prod
and silently kills the seed transaction (as happened 2026-08-08).

Usage:
    python apps/api/scripts/validate_all_skill_packs.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
PACKS_DIR = APPS_API / "app/modules/guard/skill_packs"
sys.path.insert(0, str(APPS_API))

from app.modules.guard.enforcement import validate_pack  # noqa: E402


def main() -> int:
    failed: list[str] = []
    packs = sorted(PACKS_DIR.glob("*.json"))
    if not packs:
        print(f"No packs found in {PACKS_DIR}", file=sys.stderr)
        return 1

    for path in packs:
        try:
            pack = json.loads(path.read_text())
            validate_pack(pack, source=path.name)
            print(f"  OK   {path.name} · {len(pack['rules'])} rules")
        except Exception as exc:  # noqa: BLE001 — surface every failure
            print(f"  FAIL {path.name}: {exc}", file=sys.stderr)
            failed.append(path.name)

    if failed:
        print(f"\n{len(failed)} pack(s) failed validation.", file=sys.stderr)
        return 1
    print(f"\nAll {len(packs)} packs valid.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
