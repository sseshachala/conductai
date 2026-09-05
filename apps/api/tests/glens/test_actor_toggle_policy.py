"""#1303 — actor ActionSpec + ToolDef parity for enable_policy + disable_policy.

Propose-path only; live-DB confirm+dispatch is covered by the actor
substrate integration suite.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_WS = "00000000-0000-0000-0000-000000000000"


def _ctx(**over):
    base = dict(
        db=MagicMock(),
        workspace_id=_WS,
        clerk_user_id="user_abc",
        user_email="user@example.com",
        session_id=None,
        agent_identity_id=None,
        surface="lens",
    )
    base.update(over)
    return ActionCtx(**base)


def _fake_custom_rule(rule_id="r-1", enabled=True, description="Test rule"):
    return SimpleNamespace(
        rule_id=rule_id,
        enabled=enabled,
        body={"description": description, "action": "block"},
    )


def test_enable_policy_actionspec_registered():
    spec = default_action_registry.get("enable_policy")
    assert spec is not None
    assert spec.guard_permission == "guard.policies.edit"


def test_disable_policy_actionspec_registered():
    spec = default_action_registry.get("disable_policy")
    assert spec is not None
    assert spec.guard_permission == "guard.policies.edit"


def test_both_tooldefs_registered():
    for name in ("enable_policy", "disable_policy"):
        tool = default_registry.get(name)
        assert tool is not None, f"missing ToolDef: {name}"
        assert "lens" in tool.tags
        assert "actor" in tool.tags


def test_propose_rejects_empty_rule_id():
    spec = default_action_registry.get("enable_policy")
    out = spec.propose(_ctx(), {})
    assert out.rejected
    assert "rule_id required" in (out.reason or "")


def test_propose_rejects_unknown_rule():
    spec = default_action_registry.get("disable_policy")
    ctx = _ctx()
    ctx.db.get.return_value = None
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=None):
        out = spec.propose(ctx, {"rule_id": "r-nope"})
    assert out.rejected
    assert "No policy matches rule_id" in (out.reason or "")


def test_propose_rejects_no_op_enable():
    """Enabling an already-enabled rule should fail — user should know."""
    spec = default_action_registry.get("enable_policy")
    ctx = _ctx()
    fake = _fake_custom_rule(enabled=True)
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=("custom", fake)):
        out = spec.propose(ctx, {"rule_id": "r-1"})
    assert out.rejected
    assert "already enabled" in (out.reason or "")


def test_propose_rejects_no_op_disable():
    spec = default_action_registry.get("disable_policy")
    ctx = _ctx()
    fake = _fake_custom_rule(enabled=False)
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=("custom", fake)):
        out = spec.propose(ctx, {"rule_id": "r-1"})
    assert out.rejected
    assert "already disabled" in (out.reason or "")


def test_propose_disable_pack_requires_reason():
    """Disabling a pack rule requires a reason — compliance exception."""
    spec = default_action_registry.get("disable_policy")
    ctx = _ctx()
    ctx.db.get.return_value = None  # no existing override → currently enabled
    pack_row = ({"id": "r-1", "description": "SOC2 rule"}, SimpleNamespace(pack_slug="conduct-soc2"))
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=("pack", pack_row)):
        out = spec.propose(ctx, {"rule_id": "r-1"})
    assert out.rejected
    assert "requires a reason" in (out.reason or "")


def test_propose_disable_pack_with_reason_succeeds():
    spec = default_action_registry.get("disable_policy")
    ctx = _ctx()
    ctx.db.get.return_value = None
    pack_row = ({"id": "r-1", "description": "SOC2 rule"}, SimpleNamespace(pack_slug="conduct-soc2"))
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=("pack", pack_row)):
        out = spec.propose(ctx, {"rule_id": "r-1", "reason": "Vendor exception"})
    assert not out.rejected
    assert "Disable policy 'SOC2 rule'" in out.summary
    assert out.resolved_input == {
        "rule_id": "r-1",
        "kind": "pack",
        "target_enabled": False,
        "reason": "Vendor exception",
    }


def test_propose_enable_custom_success():
    spec = default_action_registry.get("enable_policy")
    ctx = _ctx()
    fake = _fake_custom_rule(enabled=False, description="Custom rule")
    with patch("app.modules.glens.actor.registrations.toggle_policy._resolve_policy",
               return_value=("custom", fake)):
        out = spec.propose(ctx, {"rule_id": "r-1"})
    assert not out.rejected
    assert "Enable policy 'Custom rule'" in out.summary
    assert out.resolved_input["target_enabled"] is True
    assert out.resolved_input["kind"] == "custom"
