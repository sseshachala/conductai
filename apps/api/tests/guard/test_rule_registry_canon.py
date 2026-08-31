"""Regression canon — every seeded Guard rule across every skill pack
validates against the engine's contract.

Guards against the class of bugs #1482 flagged in the vibe-code audit:
- Malformed rules shipped in a pack (missing action / id / message)
- Duplicate rule IDs within a pack (silent last-wins in the engine)
- Actions outside VALID_ACTIONS (engine ignores → advertised policy is a lie)
- Personas outside PERSONAS (rule never fires — dead policy)
- Invalid regex in match_pattern (crashes matcher at first request)
- Non-overridable rules missing required guard fields

Does NOT verify semantic behavior — that's what the Guard canon (task 4)
covers with end-to-end BLOCK/WARN/ALLOW round-trips. This is the "every
rule ships intact" smoke net.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.modules.guard.policy_engine import PERSONAS, VALID_ACTIONS

PACKS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "guard"
    / "skill_packs"
)
PACK_FILES = sorted(PACKS_DIR.glob("*.json"))

# 'inject' is retired at compute_policy time (rewritten to audit +
# inject_guidance=True) but remains a valid authoring action in pack files.
AUTHORING_ACTIONS = VALID_ACTIONS  # already includes inject
VALID_SEVERITIES = {"info", "low", "medium", "high", "critical", "warning"}


def _load(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


_PACKS = [(p.stem, _load(p)) for p in PACK_FILES]

_PACK_PARAMS = [
    pytest.param(slug, pack, id=slug) for slug, pack in _PACKS
]

_RULE_PARAMS = [
    pytest.param(slug, rule, id=f"{slug}/{rule.get('id', 'noid')}")
    for slug, pack in _PACKS
    for rule in pack.get("rules", [])
]


# ── Sanity: packs actually loaded ───────────────────────────────────────────

def test_pack_files_discovered():
    assert PACK_FILES, f"No pack files under {PACKS_DIR}"


def test_rules_discovered():
    assert _RULE_PARAMS, "No rules extracted from any pack — something is wrong"


# ── Per-pack ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug,pack", _PACK_PARAMS)
def test_pack_has_top_level_fields(slug, pack):
    assert pack.get("slug"), f"{slug}: missing top-level slug"
    assert pack.get("name"), f"{slug}: missing top-level name"
    assert pack.get("version"), f"{slug}: missing top-level version"
    assert isinstance(pack.get("rules"), list), f"{slug}: rules must be a list"


@pytest.mark.parametrize("slug,pack", _PACK_PARAMS)
def test_pack_slug_matches_filename(slug, pack):
    assert pack["slug"] == slug, f"file {slug}.json declares slug {pack['slug']!r}"


@pytest.mark.parametrize("slug,pack", _PACK_PARAMS)
def test_pack_rule_ids_are_unique(slug, pack):
    ids = [r["id"] for r in pack.get("rules", []) if "id" in r]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, f"{slug}: duplicate rule ids {dupes}"


# ── Per-rule ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_rule_has_required_fields(slug, rule):
    assert rule.get("id"), f"{slug}: rule missing id"
    assert rule.get("action"), f"{slug}/{rule.get('id')}: missing action"
    assert rule.get("message"), f"{slug}/{rule.get('id')}: missing message"


@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_rule_action_is_valid(slug, rule):
    action = rule.get("action")
    assert action in AUTHORING_ACTIONS, (
        f"{slug}/{rule.get('id')}: invalid action {action!r} "
        f"(must be one of {sorted(AUTHORING_ACTIONS)})"
    )


@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_rule_persona_is_valid(slug, rule):
    persona = rule.get("persona")
    if persona is None:
        return
    values = persona if isinstance(persona, list) else [persona]
    for p in values:
        assert p in PERSONAS, (
            f"{slug}/{rule.get('id')}: unknown persona {p!r} "
            f"(must be one of {PERSONAS})"
        )


@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_rule_severity_is_valid(slug, rule):
    sev = rule.get("severity")
    if sev is None:
        return
    assert sev in VALID_SEVERITIES, (
        f"{slug}/{rule.get('id')}: unknown severity {sev!r} "
        f"(must be one of {sorted(VALID_SEVERITIES)})"
    )


@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_rule_match_pattern_compiles(slug, rule):
    pattern = rule.get("match_pattern")
    if pattern is None:
        return
    try:
        re.compile(pattern)
    except re.error as e:
        pytest.fail(
            f"{slug}/{rule.get('id')}: match_pattern is invalid regex — {e}"
        )


@pytest.mark.parametrize("slug,rule", _RULE_PARAMS)
def test_non_overridable_rules_have_message_and_persona(slug, rule):
    """Non-overridable rules are the ones that must fire — they must at
    minimum tell the caller why and be scoped to a persona so the engine
    knows when to evaluate them."""
    if not rule.get("non_overridable"):
        return
    assert rule.get("message"), f"{slug}/{rule.get('id')}: non-overridable rule missing message"
    assert rule.get("persona") is not None, (
        f"{slug}/{rule.get('id')}: non-overridable rule missing persona scoping"
    )
