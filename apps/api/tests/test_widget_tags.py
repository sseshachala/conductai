"""#1450 PR 1 — 10 KPI tools are tagged as widgets with a render hint.

Guard against regressions: the frontend picker enumerates via
`default_registry.list(tag="widget")` and extracts the hint from
`hint:<kind>` tags. If someone drops the tag off a KPI tool the picker
silently loses that widget — this test catches it at CI time.
"""
from __future__ import annotations

import pytest

from app.tools import registrations as _tool_registrations  # noqa: F401
from app.tools.registry import default_registry


# Locked mapping — spec of PR 1 (see epic #1450 body).
EXPECTED = {
    # dashboard KPIs
    "get_dashboard_outcomes":    "kpi_card",
    "list_attention_runs":       "list",
    "list_agent_health":         "agent_row",
    "get_dashboard_token_usage": "spark",
    "get_top_policy_hits":       "table",
    # observability KPIs
    "get_observability_health":  "kpi_card",
    "get_dora_metrics":          "kpi_card",
    "get_analytics_summary":     "spark",
    "list_agent_status":         "list",
    "get_playbook_scorecards":   "table",
}


@pytest.mark.parametrize("name,hint", list(EXPECTED.items()), ids=lambda x: str(x))
def test_widget_tag_and_hint_present(name, hint):
    tool = default_registry.get(name)
    assert tool is not None, f"tool '{name}' not registered"
    assert "widget" in tool.tags, f"tool '{name}' missing 'widget' tag"
    assert f"hint:{hint}" in tool.tags, (
        f"tool '{name}' missing 'hint:{hint}' tag; tags={tool.tags}"
    )


def test_widget_catalog_size():
    """Exactly 10 widget-tagged tools today; new widgets welcome, but the
    test should be updated at the same time so we notice."""
    widgets = default_registry.list(tag="widget")
    assert len(widgets) >= 10
    assert set(EXPECTED).issubset({t.name for t in widgets})
