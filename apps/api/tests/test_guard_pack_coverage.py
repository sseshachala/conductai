"""Pack rule → fixture coverage ratchet — #1263.

Every seeded pack rule under
  app/modules/guard/skill_packs/conduct-*.json
should have at least one fixture case in
  tests/fixtures/guard_packs/<pack-name>.yaml
so `test_guard_pack_matrix.py` can exercise it.

This test enforces a one-way ratchet: the uncovered count cannot grow.
When you add a rule to a pack, either add a fixture case for it or
raise COVERAGE_ALLOWANCE with a comment on the follow-up ticket. When
you add fixture cases for existing gaps, lower COVERAGE_ALLOWANCE by
the same count so future regressions are still detected.

Current gap: 66 rules across conduct-base (37), conduct-owasp (9),
conduct-prompt-injection (10), conduct-iso-42001 (2), conduct-irs-1075
(1), conduct-life-sciences (1), conduct-network-ops (4, no fixture
file), conduct-support-ops (2, no fixture file).

Ratchet down as fixtures land. Never raise without a linked issue.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

PACKS_DIR = Path(__file__).parent.parent / "app" / "modules" / "guard" / "skill_packs"
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "guard_packs"

# One-way ratchet — lower this when fixture cases are added, never raise
# without documenting the reason in a linked follow-up issue.
COVERAGE_ALLOWANCE = 66

# One-way ratchet — number of covered rules that still lack a negative
# case (expected: allow). Every rule that fires needs at least one
# adjacent-but-benign fixture case so we catch false positives before
# they ship. Lower as negative cases are added.
NEGATIVE_CASE_ALLOWANCE = 56


def _load_seeded_rules() -> dict[str, set[str]]:
    """Return {pack_name: {rule_id, ...}} for every conduct-*.json pack."""
    out: dict[str, set[str]] = {}
    for p in sorted(PACKS_DIR.glob("conduct-*.json")):
        pack = json.loads(p.read_text())
        rules = pack.get("rules", [])
        out[p.stem] = {r["id"] for r in rules if isinstance(r, dict) and "id" in r}
    return out


def _load_covered_rules() -> dict[str, set[str]]:
    """Return {pack_name: {rule_id, ...}} for rules with at least one fixture case."""
    out: dict[str, set[str]] = {}
    for f in sorted(FIXTURES_DIR.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text()) or {}
        cases = doc.get("cases", []) or []
        covered: set[str] = set()
        for c in cases:
            if not isinstance(c, dict):
                continue
            expects = c.get("expects") or {}
            rid = expects.get("rule_id") or c.get("rule_id")
            if rid:
                covered.add(rid)
        out[f.stem] = covered
    return out


def _load_case_balance() -> dict[tuple[str, str], dict[str, int]]:
    """Return {(pack, rule_id): {'positive': N, 'negative': N}}.

    Positive = case with any expected action other than 'allow' (block, warn,
    audit — the rule fires). Negative = case with expected: allow (rule
    does NOT fire on adjacent-but-benign input — the false-positive canary).
    """
    out: dict[tuple[str, str], dict[str, int]] = {}
    for f in sorted(FIXTURES_DIR.glob("*.yaml")):
        doc = yaml.safe_load(f.read_text()) or {}
        for c in doc.get("cases", []) or []:
            if not isinstance(c, dict):
                continue
            expects = c.get("expects") or {}
            rid = expects.get("rule_id") or c.get("rule_id")
            if not rid:
                continue
            exp = expects.get("action") or c.get("expected")
            rec = out.setdefault((f.stem, rid), {"positive": 0, "negative": 0})
            if exp == "allow":
                rec["negative"] += 1
            elif exp:
                rec["positive"] += 1
    return out


def _compute_gaps() -> list[tuple[str, str]]:
    seeded = _load_seeded_rules()
    covered = _load_covered_rules()
    gaps: list[tuple[str, str]] = []
    for pack_name in sorted(seeded):
        pack_covered = covered.get(pack_name, set())
        missing = seeded[pack_name] - pack_covered
        for rule_id in sorted(missing):
            gaps.append((pack_name, rule_id))
    return gaps


def test_pack_rule_coverage_does_not_regress():
    gaps = _compute_gaps()
    by_pack: dict[str, int] = {}
    for pack, _ in gaps:
        by_pack[pack] = by_pack.get(pack, 0) + 1
    summary = ", ".join(f"{p}={n}" for p, n in sorted(by_pack.items()))
    assert len(gaps) <= COVERAGE_ALLOWANCE, (
        f"Guard pack coverage regressed: {len(gaps)} rules uncovered "
        f"(allowance {COVERAGE_ALLOWANCE}). Add a fixture case in "
        f"tests/fixtures/guard_packs/<pack>.yaml for the new rule, or "
        f"raise COVERAGE_ALLOWANCE with a linked issue. "
        f"By pack: {summary}. First 10 gaps: {gaps[:10]}"
    )


def test_covered_rules_have_negative_case():
    """Every fixture-covered rule should have at least one negative case
    (expected: allow). Without one the rule may over-fire on benign input
    and the matrix has no signal — that is a false positive waiting to ship.
    """
    balance = _load_case_balance()
    missing = [
        (pack, rule) for (pack, rule), v in sorted(balance.items()) if v["negative"] == 0
    ]
    by_pack: dict[str, int] = {}
    for pack, _ in missing:
        by_pack[pack] = by_pack.get(pack, 0) + 1
    summary = ", ".join(f"{p}={n}" for p, n in sorted(by_pack.items(), key=lambda x: -x[1]))
    assert len(missing) <= NEGATIVE_CASE_ALLOWANCE, (
        f"Guard pack negative-case coverage regressed: {len(missing)} covered "
        f"rules lack a negative (expected: allow) case — allowance is "
        f"{NEGATIVE_CASE_ALLOWANCE}. Add a benign-input case for the new "
        f"rule so we catch false positives before they ship. "
        f"By pack: {summary}. First 10 gaps: {missing[:10]}"
    )


def test_all_fixture_files_have_matching_pack_json():
    """Fixture YAMLs must reference a real pack. Catches typo drift."""
    fixture_names = {f.stem for f in FIXTURES_DIR.glob("*.yaml")}
    pack_names = {p.stem for p in PACKS_DIR.glob("conduct-*.json")}
    orphans = fixture_names - pack_names
    assert not orphans, (
        f"Fixture YAML(s) do not match any pack JSON: {sorted(orphans)}. "
        f"Rename the fixture or add the pack under skill_packs/."
    )
