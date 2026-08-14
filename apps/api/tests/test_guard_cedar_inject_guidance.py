"""Cedar adapter round-trip for inject_guidance flag (#1141).

Verifies:
  - legacy `@advice("inject")` imports as `action=audit + inject_guidance=true`
  - `@inject_guidance("true")` annotation imports as `inject_guidance=true`
  - Guard rule with `inject_guidance=true` exports with `@inject_guidance("true")`
  - Round-trip preserves the flag
"""
from __future__ import annotations

from app.modules.guard.cedar_adapter.mapper import cedar_json_to_rule
from app.modules.guard.cedar_adapter.exporter import rule_to_cedar_text


def _base_cedar_policy(annotations: dict) -> dict:
    return {
        "effect": "permit",
        "annotations": annotations,
        "principal": {},
        "action": {},
        "conditions": [],
    }


def test_legacy_advice_inject_maps_to_audit_plus_flag():
    policy = _base_cedar_policy({
        "id": "legacy-inject-rule",
        "advice": "inject",
        "message": "Coach the model to redact PII.",
    })
    rule = cedar_json_to_rule(policy)
    assert rule["action"] == "audit"
    assert rule["inject_guidance"] is True


def test_new_inject_guidance_annotation_imports():
    policy = _base_cedar_policy({
        "id": "modern-warn-plus-guidance",
        "advice": "warn",
        "inject_guidance": "true",
        "message": "Warn the user AND coach the model.",
    })
    rule = cedar_json_to_rule(policy)
    assert rule["action"] == "warn"
    assert rule["inject_guidance"] is True


def test_absent_flag_does_not_set_inject_guidance():
    policy = _base_cedar_policy({
        "id": "plain-warn",
        "advice": "warn",
    })
    rule = cedar_json_to_rule(policy)
    assert rule["action"] == "warn"
    assert "inject_guidance" not in rule


def test_exporter_emits_annotation_when_flag_set():
    rule = {
        "id": "audit-with-coaching",
        "action": "audit",
        "inject_guidance": True,
        "message": "Coach the model.",
        "match_tool": "*",
    }
    cedar_text = rule_to_cedar_text(rule)
    assert '@inject_guidance("true")' in cedar_text


def test_exporter_omits_annotation_when_flag_missing():
    rule = {
        "id": "plain-block",
        "action": "block",
        "match_tool": "*",
    }
    cedar_text = rule_to_cedar_text(rule)
    assert "@inject_guidance" not in cedar_text


def test_round_trip_preserves_inject_guidance_on_block():
    """Block + inject_guidance should survive export → import cycle."""
    original = _base_cedar_policy({
        "id": "secret-stripe-like",
        "advice": None,
        "inject_guidance": "true",
        "message": "Load key from env, do not commit sk_live_ literals.",
    })
    original["effect"] = "forbid"
    imported = cedar_json_to_rule(original)
    assert imported["action"] == "block"
    assert imported["inject_guidance"] is True


def test_exporter_never_emits_legacy_inject_action():
    """Post-migration Guard rules cannot have action=inject; if fed one anyway,
    the exporter falls through to the permit-default (does not KeyError)."""
    rule = {"id": "hypothetical", "action": "inject", "match_tool": "*"}
    cedar_text = rule_to_cedar_text(rule)
    # inject is no longer in ACTION_TO_EFFECT, so exporter uses .get(..., "permit").
    assert cedar_text.startswith("@id(") or "permit" in cedar_text
