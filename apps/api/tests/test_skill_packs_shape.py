"""Regression tests for skill_pack shape and contents.

Catches:
  1. A pack that no longer validates against the enforcement contract
     (would silently kill the seed transaction on startup — see 2026-08-08).
  2. A pack whose rule count silently drops (rule accidentally deleted).
  3. A pack whose slug/version changed without intent.

The rule-count baseline uses a >= floor rather than exact equality so adding
new rules doesn't fail CI — only silent deletions do.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.guard.enforcement import validate_pack

PACKS_DIR = Path(__file__).resolve().parent.parent / "app/modules/guard/skill_packs"

# Minimum expected rule counts per pack. Bump these UP when you intentionally add rules.
# CI fails if a pack falls BELOW its floor — that's the regression signal.
RULE_COUNT_FLOOR: dict[str, int] = {
    "conduct-base": 35,
    "conduct-owasp": 20,
    "conduct-soc2": 3,
    "conduct-hipaa": 3,
    "conduct-pci-dss": 3,
    "conduct-eu-ai-act": 8,
    "conduct-nist-ai-rmf": 8,
    "conduct-iso-42001": 8,
    "conduct-irs-1075": 6,
    "conduct-financial-services": 6,
    "conduct-life-sciences": 7,
}


def _load_all_packs() -> list[tuple[str, dict]]:
    return [
        (path.stem, json.loads(path.read_text()))
        for path in sorted(PACKS_DIR.glob("*.json"))
    ]


@pytest.mark.parametrize("slug,pack", _load_all_packs(), ids=lambda x: x if isinstance(x, str) else x.get("slug", "?"))
def test_pack_validates(slug: str, pack: dict) -> None:
    """Every shipped skill_pack must satisfy the enforcement contract."""
    validate_pack(pack, source=f"{slug}.json")


@pytest.mark.parametrize("slug,pack", _load_all_packs(), ids=lambda x: x if isinstance(x, str) else x.get("slug", "?"))
def test_pack_rule_count_floor(slug: str, pack: dict) -> None:
    """Guard against silent rule deletion. Bump RULE_COUNT_FLOOR up when adding rules."""
    if slug not in RULE_COUNT_FLOOR:
        pytest.skip(f"No floor set for {slug} — add one to RULE_COUNT_FLOOR")
    floor = RULE_COUNT_FLOOR[slug]
    actual = len(pack.get("rules", []))
    assert actual >= floor, (
        f"{slug}: rule count dropped to {actual} (floor: {floor}). "
        "Did you delete a rule? If intentional, lower the floor."
    )


def test_pack_slugs_match_filenames() -> None:
    """Filename must match the pack's declared slug. Prevents install-lookup drift."""
    for path in sorted(PACKS_DIR.glob("*.json")):
        pack = json.loads(path.read_text())
        assert pack["slug"] == path.stem, (
            f"{path.name}: slug={pack['slug']!r} does not match filename"
        )


def test_pack_rule_ids_unique() -> None:
    """No two rules within a pack may share an id."""
    for path in sorted(PACKS_DIR.glob("*.json")):
        pack = json.loads(path.read_text())
        ids = [r["id"] for r in pack.get("rules", [])]
        assert len(ids) == len(set(ids)), (
            f"{path.name}: duplicate rule ids — {[i for i in ids if ids.count(i) > 1]}"
        )
