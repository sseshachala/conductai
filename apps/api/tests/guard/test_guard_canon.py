"""Guard regression canon — structural ratchets + coverage manifest.

# Why this file exists

Same reasoning as tests/glens/test_lens_canon.py: recent Guard fixes already
ship regression tests per-PR. This file (a) documents the canon as a
coverage manifest so an engineer looking for "the Guard regression tests"
finds one authoritative index, and (b) adds structural ratchets that catch
classes of regression the per-PR tests miss (silent rule removal,
non-overridable action relaxation, pack-catalog drift).

Delete an item from the manifest only after confirming the covering test
still exercises the behavior end-to-end.

# Coverage manifest

| # | Canon behavior                                                    | Test file                                        |
|---|-------------------------------------------------------------------|--------------------------------------------------|
| 1 | Policy BLOCK → 403 + audit event + hash chain intact              | tests/guard/test_policy_composed.py              |
| 2 | Policy WARNING → 200 + audit + warning surfaced                   | tests/guard/test_policy_composed.py              |
| 3 | Policy ALLOW → 200 + audit                                        | tests/guard/test_policy_composed.py              |
| 4 | Policy engine crash → current fail-open behavior                  | GAP — decision pending (#1482 item 6)            |
| 5 | Approval Slack button → resume correct run                        | tests/guard/test_policy_composed.py (partial)    |
| 6 | Approval reject → run terminates + audit                          | GAP — reject-path integration test               |
| 7 | Kill switch → all new LLM calls halt in <5s                       | GAP — kill switch endpoint not yet exposed       |
| 8 | Budget exceeded → BLOCK + notification                            | tests/guard/test_proxy_budget_check.py           |
| 9 | Rate limit → 429 with retry-after                                 | tests/guard/test_rate_limit_smoke.py, burst_smoke |
|10 | Cross-workspace isolation — WS A can't read WS B policies         | GAP — dedicated isolation test not yet written   |
|11 | Rule sync from pack → new rules land in DB                        | tests/guard/test_policy_sources.py               |
|12 | MCP guard_check → returns BLOCKED/WARNING/ok matching policy      | tests/guard/test_executor_guard_check.py         |
|13 | MCP guard_activity → writes audit event                           | GAP — dedicated activity write test              |
|14 | Vault: credential write/read/rotate                               | GAP — credentials integration test               |
|15 | Hash-chain verify endpoint detects tampering                      | GAP — verify endpoint not yet exposed            |
|16 | Persona routing — correct persona applied to context              | tests/guard/test_policy_composed.py              |
|17 | LLM proxy: request + response logged + no PII leak                | tests/guard/test_guarded_llm_call.py, stream     |
|18 | Discovery daemon: registers new agent identity                    | GAP — daemon integration test                    |
|19 | Findings sync: SIEM export includes hash-chain proof              | GAP — SIEM export not yet built                  |
|20 | Compliance pack install/uninstall clean                           | tests/guard/test_policy_sources.py (partial)     |

Rule catalog integrity:                                              | tests/guard/test_rule_registry_canon.py           |

GAPs are true gaps (feature not built, or test not yet written). Each earns
a filed follow-up issue when picked up.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.modules.guard.policy_engine import PERSONAS, VALID_ACTIONS

PACKS_DIR = (
    Path(__file__).resolve().parent.parent.parent
    / "app"
    / "modules"
    / "guard"
    / "skill_packs"
)


def _load_all_packs() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted(PACKS_DIR.glob("*.json"))]


def _all_rules() -> list[tuple[str, dict]]:
    out = []
    for pack in _load_all_packs():
        for rule in pack.get("rules", []):
            out.append((pack.get("slug", "?"), rule))
    return out


# ── Structural ratchets ────────────────────────────────────────────────────
# Snapshot as-of 2026-08-30. Ratchet upward as packs/rules are added, never
# down. A drop = someone silently removed a rule or a whole pack; investigate
# before merging.

_PACK_COUNT_FLOOR = 15
_RULE_COUNT_FLOOR = 183
_NON_OVERRIDABLE_COUNT_FLOOR = 10
_CRITICAL_COUNT_FLOOR = 60

# The foundation pack must always exist; workspaces bootstrap against it.
_REQUIRED_PACK_SLUGS = frozenset({"conduct-base"})


def test_pack_count_meets_floor():
    packs = _load_all_packs()
    assert len(packs) >= _PACK_COUNT_FLOOR, (
        f"Guard pack count dropped to {len(packs)} "
        f"(floor is {_PACK_COUNT_FLOOR}) — a pack was silently removed"
    )


def test_rule_count_meets_floor():
    rules = _all_rules()
    assert len(rules) >= _RULE_COUNT_FLOOR, (
        f"Guard rule count dropped to {len(rules)} "
        f"(floor is {_RULE_COUNT_FLOOR}) — rules were silently removed"
    )


def test_non_overridable_count_meets_floor():
    """Non-overridable rules are the ones the platform guarantees. Losing
    one silently = a compliance regression that would show up only under
    audit — worst class of bug."""
    non_overr = [r for _, r in _all_rules() if r.get("non_overridable")]
    assert len(non_overr) >= _NON_OVERRIDABLE_COUNT_FLOOR, (
        f"Non-overridable rule count dropped to {len(non_overr)} "
        f"(floor is {_NON_OVERRIDABLE_COUNT_FLOOR})"
    )


def test_critical_severity_count_meets_floor():
    critical = [r for _, r in _all_rules() if r.get("severity") == "critical"]
    assert len(critical) >= _CRITICAL_COUNT_FLOOR, (
        f"Critical-severity rule count dropped to {len(critical)} "
        f"(floor is {_CRITICAL_COUNT_FLOOR})"
    )


def test_required_pack_slugs_all_present():
    slugs = {pack.get("slug") for pack in _load_all_packs()}
    missing = _REQUIRED_PACK_SLUGS - slugs
    assert not missing, f"Required packs missing: {sorted(missing)}"


def test_non_overridable_rules_are_block_actions():
    """A non-overridable rule with a non-block action is a contradiction:
    'you can't override this' but 'we'll only audit / warn'. The engine
    treats non-overridable as a guarantee — the action must match."""
    offenders = [
        (slug, r.get("id"), r.get("action"))
        for slug, r in _all_rules()
        if r.get("non_overridable") and r.get("action") != "block"
    ]
    assert not offenders, (
        f"Non-overridable rules with non-block action: {offenders}"
    )


def test_valid_actions_constant_hasnt_regressed():
    """The engine's action vocabulary is a contract with every pack author.
    Adding is fine; removing an action silently orphans rules across every
    pack that uses it."""
    required = {"audit", "warn", "approval", "block"}
    missing = required - VALID_ACTIONS
    assert not missing, f"VALID_ACTIONS lost: {sorted(missing)}"


def test_personas_constant_hasnt_regressed():
    """Same guarantee for persona vocabulary — every rule's persona field
    must resolve to a known name."""
    required = {"agent", "proxy"}
    missing = required - set(PERSONAS)
    assert not missing, f"PERSONAS lost: {sorted(missing)}"


def test_every_pack_has_at_least_one_rule():
    """A pack with zero rules is dead weight in the catalog — usually a
    packaging accident."""
    empty = [pack.get("slug") for pack in _load_all_packs() if not pack.get("rules")]
    assert not empty, f"Packs with zero rules: {empty}"
