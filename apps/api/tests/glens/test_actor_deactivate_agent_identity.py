"""#1304 — actor ActionSpec + ToolDef parity for deactivate_agent_identity.

Propose-path only; live-DB confirm+dispatch is covered by the actor
substrate integration suite.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


_WS = "00000000-0000-0000-0000-000000000000"
_AGENT = "agent-uuid-1"


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


def _fake_agent(name="prod-cli", provider="anthropic", lifecycle_state="active"):
    return SimpleNamespace(
        id=_AGENT,
        name=name,
        provider=provider,
        lifecycle_state=lifecycle_state,
    )


def _mock_db_returning(agent):
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = agent
    return db


def test_deactivate_actionspec_registered():
    spec = default_action_registry.get("deactivate_agent_identity")
    assert spec is not None
    assert spec.guard_permission == "platform.members.manage"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_deactivate_tooldef_registered():
    tool = default_registry.get("deactivate_agent_identity")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_propose_rejects_empty_agent_id():
    spec = default_action_registry.get("deactivate_agent_identity")
    out = spec.propose(_ctx(), {})
    assert out.rejected
    assert "agent_id required" in (out.reason or "")


def test_propose_rejects_unknown_agent():
    spec = default_action_registry.get("deactivate_agent_identity")
    db = _mock_db_returning(None)
    out = spec.propose(_ctx(db=db), {"agent_id": _AGENT})
    assert out.rejected
    assert "No agent identity matches id" in (out.reason or "")


def test_propose_rejects_already_deactivated():
    spec = default_action_registry.get("deactivate_agent_identity")
    db = _mock_db_returning(_fake_agent(lifecycle_state="deactivated"))
    out = spec.propose(_ctx(db=db), {"agent_id": _AGENT})
    assert out.rejected
    assert "already deactivated" in (out.reason or "")


def test_propose_success_shape():
    spec = default_action_registry.get("deactivate_agent_identity")
    db = _mock_db_returning(_fake_agent(name="prod-cli", provider="anthropic"))
    out = spec.propose(_ctx(db=db), {"agent_id": _AGENT})
    assert not out.rejected
    assert "Deactivate agent identity 'prod-cli' (anthropic)" == out.summary
    assert out.resolved_input == {
        "agent_id": _AGENT,
        "agent_name": "prod-cli",
        "provider": "anthropic",
        "reason": None,
    }


def test_propose_reason_surfaces_in_summary():
    spec = default_action_registry.get("deactivate_agent_identity")
    db = _mock_db_returning(_fake_agent())
    out = spec.propose(_ctx(db=db), {"agent_id": _AGENT, "reason": "Credential leaked"})
    assert not out.rejected
    assert "— Credential leaked" in out.summary
    assert out.resolved_input["reason"] == "Credential leaked"
