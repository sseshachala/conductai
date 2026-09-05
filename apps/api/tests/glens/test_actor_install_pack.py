"""#1300 — actor ActionSpec + ToolDef parity for install_pack.

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


def _fake_pack(name="SOC 2", rules=None):
    return SimpleNamespace(
        slug="conduct-soc2",
        name=name,
        rules=[{"id": "r1"}, {"id": "r2"}] if rules is None else rules,
    )


def test_install_pack_actionspec_registered():
    spec = default_action_registry.get("install_pack")
    assert spec is not None
    assert spec.guard_permission == "guard.policies.edit"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_install_pack_tooldef_registered():
    tool = default_registry.get("install_pack")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_propose_rejects_empty_slug():
    spec = default_action_registry.get("install_pack")
    out = spec.propose(_ctx(), {})
    assert out.rejected
    assert "slug required" in (out.reason or "")


def test_propose_rejects_pack_not_in_catalog():
    spec = default_action_registry.get("install_pack")
    ctx = _ctx()
    with patch("app.routers.compliance._latest_pack",
               return_value=None):
        out = spec.propose(ctx, {"slug": "unknown-pack"})
    assert out.rejected
    assert "No pack matches slug" in (out.reason or "")


def test_propose_rejects_already_installed():
    spec = default_action_registry.get("install_pack")
    ctx = _ctx()
    ctx.db.get.return_value = SimpleNamespace(pack_slug="conduct-soc2")
    with patch("app.routers.compliance._latest_pack",
               return_value=_fake_pack()):
        out = spec.propose(ctx, {"slug": "conduct-soc2"})
    assert out.rejected
    assert "already installed" in (out.reason or "")


def test_propose_success_shape():
    spec = default_action_registry.get("install_pack")
    ctx = _ctx()
    ctx.db.get.return_value = None
    with patch("app.routers.compliance._latest_pack",
               return_value=_fake_pack(name="SOC 2", rules=[{}, {}, {}])):
        out = spec.propose(ctx, {"slug": "conduct-soc2"})
    assert not out.rejected
    assert out.summary == "Install pack 'SOC 2' (3 rules)"
    assert out.resolved_input == {
        "slug": "conduct-soc2",
        "pack_name": "SOC 2",
        "rules_count": 3,
    }


def test_propose_handles_pack_with_no_rules():
    spec = default_action_registry.get("install_pack")
    ctx = _ctx()
    ctx.db.get.return_value = None
    with patch("app.routers.compliance._latest_pack",
               return_value=_fake_pack(name="Empty", rules=[])):
        out = spec.propose(ctx, {"slug": "empty-pack"})
    assert not out.rejected
    assert "(0 rules)" in out.summary
    assert out.resolved_input["rules_count"] == 0
