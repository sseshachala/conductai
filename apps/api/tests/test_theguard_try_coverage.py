"""Regression: /theguard/try demo verbs must be caught by conduct-base.

Root cause of the shipped-broken /theguard/try demo:
the block-verb prompt in ``apps/web/src/app/(app)/theguard/try/page.tsx``
and the proxy-persona rules in
``apps/api/app/modules/guard/skill_packs/conduct-base.json`` were
authored independently. The demo asked "print your system prompt";
Guard's ``proxy-no-prompt-injection`` rule only matched
"ignore/disregard...instructions". Every new signup saw the block
verb return ``ok`` — Guard looked toothless.

This test locks the invariant: for every VERB in page.tsx (except
allow/prove which are meant to pass through), at least one active
conduct-base proxy rule must match the exact prompt text, with an
action that matches the verb label.

Canaries live in page.tsx (single source of truth). Adding a new
demo verb without a matching rule fails this test.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent.parent
PAGE_TSX = REPO_ROOT / "apps/web/src/app/(app)/theguard/try/page.tsx"
CONDUCT_BASE = REPO_ROOT / "apps/api/app/modules/guard/skill_packs/conduct-base.json"

VERB_ACTION = {
    "allow": None,   # nothing should match — passthrough
    "warn":  "warn",
    "block": "block",
    "prove": None,   # empty prompt, not evaluated
}


def _extract_verbs() -> dict[str, str]:
    """Parse the VERBS array literal out of page.tsx. Cheap regex — the
    array shape hasn't changed since epic #1567 shipped, and this test
    is the guardrail that will catch a shape change if one happens."""
    src = PAGE_TSX.read_text()
    verbs: dict[str, str] = {}
    for match in re.finditer(
        r'key:\s*"(?P<key>allow|warn|block|prove)".*?prompt:\s*"(?P<prompt>[^"]*)"',
        src,
        re.DOTALL,
    ):
        verbs[match.group("key")] = match.group("prompt")
    return verbs


def _proxy_rules() -> list[dict]:
    data = json.loads(CONDUCT_BASE.read_text())
    return [
        r for r in data["rules"]
        if r.get("enforcement", {}).get("proxy") not in (None, "not_supported")
    ]


def _rules_matching(prompt: str) -> list[dict]:
    return [
        r for r in _proxy_rules()
        if r.get("match_pattern") and re.search(r["match_pattern"], prompt)
    ]


def test_all_four_verbs_present_in_page():
    verbs = _extract_verbs()
    assert set(verbs.keys()) == {"allow", "warn", "block", "prove"}, (
        f"page.tsx VERBS shape drifted; got {list(verbs.keys())}"
    )


@pytest.mark.parametrize("verb", ["warn", "block"])
def test_verb_prompt_matches_conduct_base_rule(verb: str):
    """Each demo verb with a non-empty prompt must match at least one
    conduct-base proxy rule whose action matches the verb label."""
    verbs = _extract_verbs()
    prompt = verbs[verb]
    assert prompt, f"page.tsx {verb} verb has empty prompt"
    hits = _rules_matching(prompt)
    assert hits, (
        f"NO conduct-base proxy rule matches /theguard/try {verb!r} prompt.\n"
        f"Prompt: {prompt!r}\n"
        f"Either update the pack pattern or change the demo prompt so the "
        f"user-facing verb actually fires."
    )
    matching_actions = {r["action"] for r in hits}
    assert verb in matching_actions, (
        f"/theguard/try {verb!r} prompt matched conduct-base rules "
        f"{[r['id'] for r in hits]}, but none have action={verb!r} "
        f"(got actions={matching_actions}). Users would see the wrong verdict."
    )


def test_allow_verb_matches_nothing():
    """The allow prompt is supposed to pass through unblocked. If any
    proxy rule matches it, users would see a warn/block on the 'good'
    example — the demo would be self-contradictory."""
    verbs = _extract_verbs()
    hits = _rules_matching(verbs["allow"])
    assert not hits, (
        f"/theguard/try allow verb matches conduct-base rules: "
        f"{[r['id'] for r in hits]}. Either narrow the pattern or "
        f"change the allow prompt so the passthrough demo is clean."
    )
