"""#1450 PR 4 — actor ActionSpec + ToolDef parity for propose_report.

Propose-path only; live-DB confirm+dispatch covered by the shared
substrate suite.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

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


def _no_existing(ctx):
    ctx.db.query.return_value.filter.return_value.first.return_value = None


def _fake_conflict(ctx, name="Ops"):
    ctx.db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(name=name)


def test_propose_report_actionspec_registered():
    spec = default_action_registry.get("propose_report")
    assert spec is not None
    assert spec.guard_permission == "platform.workflows.edit"
    assert callable(spec.propose)
    assert callable(spec.execute)


def test_propose_report_tooldef_registered():
    tool = default_registry.get("propose_report")
    assert tool is not None
    assert "lens" in tool.tags
    assert "actor" in tool.tags
    assert tool.annotations.read_only is False


def test_reject_empty_name():
    spec = default_action_registry.get("propose_report")
    out = spec.propose(_ctx(), {"name": "", "layout_spec": [{"tool_name": "get_dora_metrics", "hint": "kpi_card"}]})
    assert out.rejected
    assert "name required" in (out.reason or "")


def test_reject_bad_slug():
    spec = default_action_registry.get("propose_report")
    out = spec.propose(_ctx(), {
        "name": "Ops",
        "slug": "Bad Slug!",
        "layout_spec": [{"tool_name": "get_dora_metrics", "hint": "kpi_card"}],
    })
    assert out.rejected
    assert "slug" in (out.reason or "").lower()


def test_reject_empty_layout():
    spec = default_action_registry.get("propose_report")
    out = spec.propose(_ctx(), {"name": "Ops", "layout_spec": []})
    assert out.rejected
    assert "layout_spec" in (out.reason or "")


def test_reject_unknown_tool():
    spec = default_action_registry.get("propose_report")
    ctx = _ctx()
    _no_existing(ctx)
    out = spec.propose(ctx, {
        "name": "Ops",
        "layout_spec": [{"tool_name": "made_up_tool", "hint": "kpi_card"}],
    })
    assert out.rejected
    assert "not a widget-tagged tool" in (out.reason or "")


def test_reject_bad_hint():
    spec = default_action_registry.get("propose_report")
    ctx = _ctx()
    _no_existing(ctx)
    out = spec.propose(ctx, {
        "name": "Ops",
        "layout_spec": [{"tool_name": "get_dora_metrics", "hint": "sparkler"}],
    })
    assert out.rejected
    assert "hint" in (out.reason or "")


def test_reject_slug_conflict():
    spec = default_action_registry.get("propose_report")
    ctx = _ctx()
    _fake_conflict(ctx, name="Existing Ops")
    out = spec.propose(ctx, {
        "name": "Ops",
        "layout_spec": [{"tool_name": "get_dora_metrics", "hint": "kpi_card"}],
    })
    assert out.rejected
    assert "already exists" in (out.reason or "")


def test_success_derives_slug_from_name():
    spec = default_action_registry.get("propose_report")
    ctx = _ctx()
    _no_existing(ctx)
    out = spec.propose(ctx, {
        "name": "Ops Overview",
        "layout_spec": [
            {"tool_name": "get_dashboard_outcomes", "hint": "kpi_card"},
            {"tool_name": "list_attention_runs",    "hint": "list"},
        ],
    })
    assert not out.rejected, out.reason
    assert out.resolved_input["name"] == "Ops Overview"
    assert out.resolved_input["slug"] == "ops-overview"
    assert len(out.resolved_input["layout_spec"]) == 2
    assert "2 widget" in out.summary


def test_success_with_explicit_slug():
    spec = default_action_registry.get("propose_report")
    ctx = _ctx()
    _no_existing(ctx)
    out = spec.propose(ctx, {
        "name": "Ops",
        "slug": "custom-slug",
        "layout_spec": [{"tool_name": "get_dora_metrics", "hint": "kpi_card"}],
    })
    assert not out.rejected, out.reason
    assert out.resolved_input["slug"] == "custom-slug"


# ── Read-tool smoke ─────────────────────────────────────────────────────────

def test_list_report_widgets_returns_10_entries():
    tool = default_registry.get("list_report_widgets")
    assert tool is not None
    payload = tool.impl(_ctx())
    assert payload["count"] >= 10
    names = {w["tool_name"] for w in payload["widgets"]}
    assert "get_dashboard_outcomes" in names
    assert "get_dora_metrics" in names
    # every widget has a hint extracted from tags
    for w in payload["widgets"]:
        assert w["hint"] in {"kpi_card", "spark", "list", "table", "agent_row"}


def test_list_report_templates_returns_two():
    tool = default_registry.get("list_report_templates")
    assert tool is not None
    payload = tool.impl(_ctx())
    slugs = {t["slug"] for t in payload["templates"]}
    assert slugs == {"operations", "observability"}
    for t in payload["templates"]:
        assert len(t["widgets"]) >= 1
