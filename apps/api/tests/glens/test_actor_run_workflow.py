"""#1298 — actor ActionSpec + ToolDef parity for run_workflow.

Propose-path only; live-DB confirm+dispatch is covered by the follow-up
integration suite. Same shape as tests/glens/test_actor_substrate.py.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.glens.actor import default_action_registry, ActionCtx
from app.modules.glens.actor import registrations  # noqa: F401 — populate registry
from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


def _ctx(**over):
    base = dict(
        db=MagicMock(),
        workspace_id="00000000-0000-0000-0000-000000000000",
        clerk_user_id="user_abc",
        user_email="user@example.com",
        session_id=None,
        agent_identity_id=None,
        surface="lens",
    )
    base.update(over)
    return ActionCtx(**base)


def test_run_workflow_actionspec_registered():
    spec = default_action_registry.get("run_workflow")
    assert spec is not None
    assert spec.guard_permission == "platform.workflows.run"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_run_workflow_tooldef_registered():
    tool = default_registry.get("run_workflow")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_propose_rejects_empty_name():
    spec = default_action_registry.get("run_workflow")
    out = spec.propose(_ctx(), {})
    assert out.rejected
    assert "name_or_id" in (out.reason or "")


def test_propose_rejects_workflow_not_found():
    spec = default_action_registry.get("run_workflow")
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=None):
        out = spec.propose(_ctx(), {"name_or_id": "nonexistent"})
    assert out.rejected
    assert "No workflow matches" in (out.reason or "")


def test_propose_rejects_no_published_version():
    spec = default_action_registry.get("run_workflow")
    fake_wf = SimpleNamespace(
        id="w1", name="Nightly", current_version_id=None, guard_enabled=True,
    )
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=fake_wf):
        out = spec.propose(_ctx(), {"name_or_id": "Nightly"})
    assert out.rejected
    assert "no published version" in (out.reason or "").lower()


def test_propose_rejects_bad_inputs_shape():
    spec = default_action_registry.get("run_workflow")
    fake_wf = SimpleNamespace(
        id="w1", name="Nightly", current_version_id="v1", guard_enabled=True,
    )
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=fake_wf):
        out = spec.propose(_ctx(), {"name_or_id": "Nightly", "inputs": "not a dict"})
    assert out.rejected
    assert "inputs must be an object" in (out.reason or "")


def test_propose_success_shape():
    spec = default_action_registry.get("run_workflow")
    fake_wf = SimpleNamespace(
        id="w1", name="Nightly scan", current_version_id="v1", guard_enabled=True,
    )
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=fake_wf):
        out = spec.propose(_ctx(), {"name_or_id": "Nightly scan"})
    assert not out.rejected
    assert "Run 'Nightly scan' now" == out.summary
    assert out.resolved_input == {
        "workflow_id": "w1",
        "workflow_name": "Nightly scan",
        "inputs": {},
    }
    assert out.warnings == []


def test_propose_warns_when_guard_disabled():
    spec = default_action_registry.get("run_workflow")
    fake_wf = SimpleNamespace(
        id="w1", name="Nightly", current_version_id="v1", guard_enabled=False,
    )
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=fake_wf):
        out = spec.propose(_ctx(), {"name_or_id": "Nightly"})
    assert not out.rejected
    assert any("Guard is disabled" in w for w in out.warnings)


def test_propose_summary_mentions_input_count():
    spec = default_action_registry.get("run_workflow")
    fake_wf = SimpleNamespace(
        id="w1", name="X", current_version_id="v1", guard_enabled=True,
    )
    with patch("app.modules.glens.actor.registrations.run_workflow._resolve_workflow",
               return_value=fake_wf):
        out = spec.propose(_ctx(), {
            "name_or_id": "X",
            "inputs": {"foo": 1, "bar": 2, "baz": 3},
        })
    assert "3 input" in out.summary
