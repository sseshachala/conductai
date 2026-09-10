"""#1751 PR 6 — smoke test derive_surface_status against real shipped packs.

Loads conduct-base.json + conduct-hipaa.json from disk (no DB) and asserts
every rule produces a valid derived status on every PEP surface. Guards
against a future rule shape that breaks the derived function silently.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.modules.guard.enforcement import derive_gates, derive_surface_status
from app.modules.guard.pep_registry import all_surfaces


PACKS_DIR = Path(__file__).resolve().parents[2] / "app/modules/guard/skill_packs"


def _load(pack: str) -> list[dict]:
    with (PACKS_DIR / f"{pack}.json").open() as fh:
        return json.load(fh).get("rules") or []


def test_derive_surface_status_returns_valid_enum_for_every_shipped_rule():
    """Every rule × every surface must return one of the declared statuses.
    Silently returning None or a typo string would break the UI badge shelf."""
    valid = {"hard", "not_supported"}
    for pack in ("conduct-base", "conduct-hipaa"):
        rules = _load(pack)
        assert rules, f"{pack} shipped with zero rules — regression"
        for rule in rules:
            for surface in all_surfaces():
                status = derive_surface_status(rule, surface)
                assert status in valid, (
                    f"{pack}:{rule.get('id')} on {surface} → {status!r} "
                    f"(expected one of {valid})"
                )


def test_every_shipped_rule_has_at_least_one_gate():
    """derive_gates always returns a non-empty list (falls back to
    ['action']). A rule with no matcher metadata would slip through
    silently — this is the belt-and-braces check."""
    for pack in ("conduct-base", "conduct-hipaa"):
        for rule in _load(pack):
            gates = derive_gates(rule)
            assert gates, f"{pack}:{rule.get('id')} — derive_gates returned empty"


def test_at_least_one_pep_covers_every_shipped_rule():
    """Regression: no rule should be `not_supported` on every surface.
    That would mean it ships in a pack but no PEP can actually enforce
    it — dead metadata."""
    for pack in ("conduct-base", "conduct-hipaa"):
        for rule in _load(pack):
            statuses = {
                surface: derive_surface_status(rule, surface)
                for surface in all_surfaces()
            }
            hard_surfaces = [s for s, v in statuses.items() if v == "hard"]
            assert hard_surfaces, (
                f"{pack}:{rule.get('id')} — no PEP surface can enforce this rule. "
                f"Derived statuses: {statuses}"
            )
