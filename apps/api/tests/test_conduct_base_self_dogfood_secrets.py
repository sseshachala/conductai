"""Verify conduct-base v2.15.0 self-dogfood token rules.

Each rule must catch its target Conduct-issued token shape AND reject a
benign look-alike (prose that mentions the prefix without a real value).
Test constructs synthetic values at runtime so this file itself never
carries a lookup-scanner-triggering literal.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

PACK_PATH = (
    Path(__file__).parent.parent
    / "app" / "modules" / "guard" / "skill_packs" / "conduct-base.json"
)


def _hex(n: int) -> str:
    return "0123456789abcdef" * (n // 16) + "0123456789abcdef"[: n % 16]


_COND_AGT = "cond_agt_" + _hex(64)          # real CLI/agent token shape
_COND_RUN = "cond_run_" + _hex(48)          # runtime credential broker token
_COND_SHORT = "cond_agt_deadbeef"            # too short — should NOT match
_BOOSTER_LINE = '"BOOSTER_SECRET": "' + _hex(48) + '"'
_BOOSTER_NAME_ONLY = 'BOOSTER_SECRET is set via .env'  # should NOT match


@pytest.fixture(scope="module")
def rules_by_id():
    data = json.loads(PACK_PATH.read_text())
    return {r["id"]: r for r in data["rules"]}


def test_pack_version_bumped():
    data = json.loads(PACK_PATH.read_text())
    assert data["version"] == "2.15.0", (
        f"Expected pack version 2.15.0, got {data['version']}. "
        "Bump when adding rules so `conduct guard sync` picks up changes."
    )


@pytest.mark.parametrize("rule_id", ["no-conduct-tokens", "no-booster-secrets"])
def test_self_dogfood_rule_present_and_blocks(rule_id, rules_by_id):
    rule = rules_by_id.get(rule_id)
    assert rule is not None, f"Missing rule {rule_id} in conduct-base"
    assert rule["action"] == "block"
    assert rule["non_overridable"] is True
    assert rule["persona"] == "agent"


@pytest.mark.parametrize(
    "rule_id,hit_text,miss_text",
    [
        # Real 64-hex CLI token → catch. Prose + too-short suffix → miss.
        ("no-conduct-tokens", f"echo {_COND_AGT}", "tokens start with cond_agt_ prefix"),
        # cond_run_ + 48 hex → catch. Too-short suffix → miss.
        ("no-conduct-tokens", f"run_token={_COND_RUN}", _COND_SHORT),
        # BOOSTER_SECRET followed by 40+ hex value → catch. Name-only prose → miss.
        ("no-booster-secrets", _BOOSTER_LINE, _BOOSTER_NAME_ONLY),
    ],
)
def test_self_dogfood_rule_matches_target(rule_id, hit_text, miss_text, rules_by_id):
    pattern = rules_by_id[rule_id]["match_pattern"]
    assert re.search(pattern, hit_text), (
        f"Rule {rule_id} pattern {pattern!r} failed on target: {hit_text!r}"
    )
    assert not re.search(pattern, miss_text), (
        f"Rule {rule_id} pattern {pattern!r} matched benign: {miss_text!r}"
    )
