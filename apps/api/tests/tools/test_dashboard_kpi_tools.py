"""Registration + dispatch parity for the #1439 batch — dashboard +
observability KPI tools registered under the free-function convention.

Verifies every ToolDef reaches default_registry with the lens tag and
read_only annotation. Full DB paths are exercised only for a representative
subset; the rest are covered by the smoke registration check.
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


_BATCH_TOOLS = [
    "get_dashboard_outcomes",
    "list_attention_runs",
    "list_agent_health",
    "get_dashboard_token_usage",
    "get_top_policy_hits",
    "get_observability_health",
    "get_dora_metrics",
    "get_analytics_summary",
    "list_agent_status",
    "get_playbook_scorecards",
]


def test_batch_tools_registered():
    """All 10 tools appear in default_registry with the lens tag."""
    for name in _BATCH_TOOLS:
        tool = default_registry.get(name)
        assert tool is not None, f"{name} not registered"
        assert "lens" in tool.tags, f"{name} missing 'lens' tag"
        assert tool.annotations.read_only, f"{name} should be read_only"


# ── Dispatch-shape tests — one per tool, using minimal DB stubs ──────────────

class _StubQuery:
    """Chainable query stub — returns configured rows on .all(), count, scalar,
    first(). All chain methods return self."""
    def __init__(self, rows=None, count_val=0, scalar_val=0, first_val=None):
        self._rows = rows or []
        self._count = count_val
        self._scalar = scalar_val
        self._first = first_val

    def join(self, *a, **kw): return self
    def outerjoin(self, *a, **kw): return self
    def filter(self, *a, **kw): return self
    def group_by(self, *a, **kw): return self
    def order_by(self, *a, **kw): return self
    def limit(self, *a, **kw): return self
    def offset(self, *a, **kw): return self
    def subquery(self): return self
    def all(self): return self._rows
    def count(self): return self._count
    def scalar(self): return self._scalar
    def first(self): return self._first


class _StubDB:
    def __init__(self, query_map=None):
        # query_map: callable that receives args and returns _StubQuery
        self._query_map = query_map or (lambda *a, **kw: _StubQuery())
    def query(self, *a, **kw): return self._query_map(*a, **kw)
    def close(self): pass


def _patch_session(stub_db):
    """Patch app.core.database.SessionLocal to return the stub."""
    return patch("app.core.database.SessionLocal", return_value=stub_db)


def test_get_dashboard_outcomes_dispatch():
    fake_rows = [
        (SimpleNamespace(status="succeeded"), "autopilot_full"),
        (SimpleNamespace(status="failed"), "autopilot_full"),
    ]
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=fake_rows))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db), \
         patch("app.routers.insights._outcome_type", return_value="pr_opened"):
        result = lens_dispatch("get_dashboard_outcomes", '{"time_window": "last_7d"}', _CTX)
    payload = json.loads(result)
    assert payload["time_window"] == "last_7d"
    assert payload["prs_opened"] == 1
    assert payload["successful_automations"] == 1
    assert payload["failed_automations"] == 1


def test_list_attention_runs_dispatch():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="r-1", status="failed", triggered_by="scheduler",
        state={"repo": "acme/api", "trigger": "cron"}, created_at=now,
    )
    wf_id = "wf-1"
    wf_name = "Nightly scan"
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[(run, wf_id, wf_name)]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db), \
         patch("app.schemas.run._extract_trigger_summary", return_value="cron"), \
         patch("app.routers.insights._extract_repo", return_value="acme/api"):
        result = lens_dispatch("list_attention_runs", "{}", _CTX)
    payload = json.loads(result)
    assert payload["count"] == 1
    assert payload["runs"][0]["status"] == "failed"
    assert payload["runs"][0]["repo"] == "acme/api"


def test_list_agent_health_dispatch():
    """Empty aggregate — no workflows, so no last_run_status subquery either.
    Full-parity SQL exercised at manual smoke."""
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("list_agent_health", "{}", _CTX)
    payload = json.loads(result)
    assert payload["count"] == 0
    assert payload["agents"] == []


def test_get_dashboard_token_usage_dispatch():
    row = SimpleNamespace(wf_id="wf-1", wf_name="Agent A",
                          input_tokens=1000, output_tokens=500)
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("get_dashboard_token_usage", "{}", _CTX)
    payload = json.loads(result)
    assert payload["total_input_tokens"] == 1000
    assert payload["total_output_tokens"] == 500
    assert payload["total_tokens"] == 1500
    assert len(payload["by_agent"]) == 1


def test_get_top_policy_hits_dispatch():
    row = SimpleNamespace(rule_id="rule.no_prompt_injection", cnt=42)
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("get_top_policy_hits", '{"limit": 5}', _CTX)
    payload = json.loads(result)
    assert payload["hits"][0]["policy_name"] == "rule.no_prompt_injection"
    assert payload["hits"][0]["count"] == 42


def test_get_observability_health_dispatch():
    """Two chained queries — first for counts, second for last_24h rows."""
    from datetime import datetime, timezone
    calls = {"n": 0}
    def qm(*a, **kw):
        calls["n"] += 1
        return _StubQuery(rows=[SimpleNamespace(status="succeeded", created_at=datetime.now(timezone.utc))],
                          count_val=3)
    db = _StubDB(qm)
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("get_observability_health", "{}", _CTX)
    payload = json.loads(result)
    assert "active_runs" in payload
    assert "error_rate_24h" in payload


def test_get_dora_metrics_dispatch():
    totals = SimpleNamespace(total=100, succeeded=90, avg_duration=1234.0)
    trigger_row = SimpleNamespace(trigger_type="cron", runs=100, succeeded=90)
    def qm(*a, **kw):
        # First call returns totals via .first(), later returns trigger rows via .all()
        return _StubQuery(rows=[trigger_row], first_val=totals)
    db = _StubDB(qm)
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("get_dora_metrics", '{"days": 30}', _CTX)
    payload = json.loads(result)
    assert payload["window_days"] == 30
    assert payload["total_runs"] == 100
    assert payload["deployment_frequency"] == round(90 / 30, 4)
    assert payload["change_failure_rate"] == round(10 / 100, 4)


def test_get_analytics_summary_dispatch():
    totals = SimpleNamespace(
        total=50, succeeded=45, total_cost=12.50,
        total_input=10000, total_output=5000, avg_duration=800.0,
    )
    db = _StubDB(lambda *a, **kw: _StubQuery(first_val=totals))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db), \
         patch("app.routers.insights._playbook_stats", return_value=[]):
        result = lens_dispatch("get_analytics_summary", '{"days": 30}', _CTX)
    payload = json.loads(result)
    assert payload["total_runs"] == 50
    assert payload["succeeded"] == 45
    assert payload["failed"] == 5
    assert payload["total_cost_usd"] == 12.50


def test_list_agent_status_dispatch_empty():
    """No workflows in workspace → returns empty list without touching the
    per-agent join branches (which need a real SQLAlchemy subquery)."""
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("list_agent_status", "{}", _CTX)
    payload = json.loads(result)
    assert payload["count"] == 0
    assert payload["agents"] == []


def test_get_playbook_scorecards_dispatch():
    row = SimpleNamespace(
        slug="autopilot_full", grade="A", pct=95.0,
        mechanical_score=95, mechanical_max=100,
        judge_score=90, judge_max=100, judge_used=True,
    )
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=_ALLOW), \
         _patch_session(db):
        result = lens_dispatch("get_playbook_scorecards", '{"days": 30}', _CTX)
    payload = json.loads(result)
    assert payload["count"] == 1
    assert payload["scorecards"][0]["playbook_slug"] == "autopilot_full"
    assert payload["scorecards"][0]["grade"] == "A"
    assert payload["scorecards"][0]["grade_dist"]["A"] == 1
