"""Registration + dispatch parity for the #1439 dashboard + observability
KPI tools (free-function convention). Each tool wraps a computation already
in app.routers.insights; the tests verify the ToolDef reaches the registry
and the dispatch shape matches Lens chat expectations.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.mcp.lens_adapter import dispatch as lens_dispatch
from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # populate registry
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")
_ALLOW = PolicyDecision(action=PolicyAction.ALLOW, source="rule")


def test_get_dashboard_outcomes_registered():
    tool = default_registry.get("get_dashboard_outcomes")
    assert tool is not None, "get_dashboard_outcomes not registered"
    assert "lens" in tool.tags
    assert tool.annotations.read_only


def test_get_dashboard_outcomes_dispatch_shape():
    """Rows aggregate by run.status + _outcome_type: one succeeded pr_opened,
    one succeeded issue_triaged, one failed. Everything else stays zero."""
    fake_rows = [
        (SimpleNamespace(status="succeeded"), "autopilot_full"),
        (SimpleNamespace(status="succeeded"), "issue_triage"),
        (SimpleNamespace(status="failed"), "autopilot_full"),
    ]

    class _Q:
        def join(self, *a, **kw): return self
        def filter(self, *a, **kw): return self
        def all(self): return fake_rows

    class _DB:
        def query(self, *a, **kw): return _Q()
        def close(self): pass

    def _outcome(run, slug):
        if slug == "autopilot_full" and run.status == "succeeded":
            return "pr_opened"
        if slug == "issue_triage" and run.status == "succeeded":
            return "issue_triaged"
        return None

    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         patch("app.tools.registrations.lens.SessionLocal", return_value=_DB(), create=True), \
         patch("app.core.database.SessionLocal", return_value=_DB()), \
         patch("app.routers.insights._outcome_type", side_effect=_outcome):
        result = lens_dispatch("get_dashboard_outcomes", '{"time_window": "last_7d"}', _CTX)

    payload = json.loads(result)
    assert payload["time_window"] == "last_7d"
    assert payload["prs_opened"] == 1
    assert payload["issues_triaged"] == 1
    assert payload["reviews_completed"] == 0
    assert payload["incidents_investigated"] == 0
    assert payload["successful_automations"] == 2
    assert payload["failed_automations"] == 1
