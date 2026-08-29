"""Registration + shape parity for the #1439 batch — dashboard + observability
KPI tools.

See `tests/tools/_model_stubs.py` for the shared stubs. Every free-function
Lens tool test MUST use those stubs — CI leaks MagicMock into SQLAlchemy
Column attributes, and inline stubs invariably miss an op.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # populate registry
from app.tools.registry import default_registry

from tests.tools._model_stubs import StubDB, StubQuery, patch_session_and_models


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")

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


# ── Impl-shape tests — call impls directly; registration covers wiring ──────

def test_get_dashboard_outcomes_shape():
    fake_rows = [
        (SimpleNamespace(status="succeeded"), "autopilot_full"),
        (SimpleNamespace(status="failed"), "autopilot_full"),
    ]
    db = StubDB(lambda *a, **kw: StubQuery(rows=fake_rows))
    with patch_session_and_models(
        db,
        patch("app.routers.insights._outcome_type", return_value="pr_opened"),
    ):
        from app.tools.registrations.lens import get_dashboard_outcomes
        out = get_dashboard_outcomes(_CTX, time_window="last_7d")
    assert out["time_window"] == "last_7d"
    assert out["prs_opened"] == 1
    assert out["successful_automations"] == 1
    assert out["failed_automations"] == 1


def test_list_attention_runs_shape():
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="r-1", status="failed", triggered_by="scheduler",
        state={"repo": "acme/api"}, created_at=now,
    )
    db = StubDB(lambda *a, **kw: StubQuery(rows=[(run, "wf-1", "Nightly")]))
    with patch_session_and_models(
        db,
        patch("app.schemas.run._extract_trigger_summary", return_value="cron"),
        patch("app.routers.insights._extract_repo", return_value="acme/api"),
    ):
        from app.tools.registrations.lens import list_attention_runs
        out = list_attention_runs(_CTX)
    assert out["count"] == 1
    assert out["runs"][0]["status"] == "failed"


def test_list_agent_health_shape_empty():
    """Empty aggregate — proves shape without hitting the last_run_status
    subquery path (which needs a real SQLAlchemy subquery)."""
    db = StubDB(lambda *a, **kw: StubQuery(rows=[]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import list_agent_health
        out = list_agent_health(_CTX)
    assert out == {"count": 0, "agents": []}


def test_get_dashboard_token_usage_shape():
    row = SimpleNamespace(wf_id="wf-1", wf_name="A", input_tokens=1000, output_tokens=500)
    db = StubDB(lambda *a, **kw: StubQuery(rows=[row]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import get_dashboard_token_usage
        out = get_dashboard_token_usage(_CTX)
    assert out["total_input_tokens"] == 1000
    assert out["total_tokens"] == 1500
    assert len(out["by_agent"]) == 1


def test_get_top_policy_hits_shape():
    row = SimpleNamespace(rule_id="rule.no_prompt_injection", cnt=42)
    db = StubDB(lambda *a, **kw: StubQuery(rows=[row]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import get_top_policy_hits
        out = get_top_policy_hits(_CTX)
    assert out["hits"][0]["policy_name"] == "rule.no_prompt_injection"
    assert out["hits"][0]["count"] == 42


def test_get_observability_health_shape():
    db = StubDB(lambda *a, **kw: StubQuery(rows=[], count_val=0))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import get_observability_health
        out = get_observability_health(_CTX)
    for key in ("active_runs", "pending_approvals", "stale_workers",
                "succeeded_last_24h", "failed_last_24h", "total_last_24h",
                "error_rate_24h"):
        assert key in out


def test_get_dora_metrics_shape():
    totals = SimpleNamespace(total=100, succeeded=90, avg_duration=1234.0)
    db = StubDB(lambda *a, **kw: StubQuery(rows=[], first_val=totals))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import get_dora_metrics
        out = get_dora_metrics(_CTX, days=30)
    assert out["window_days"] == 30
    assert out["total_runs"] == 100
    assert out["deployment_frequency"] == round(90 / 30, 4)
    assert out["change_failure_rate"] == round(10 / 100, 4)


def test_get_analytics_summary_shape():
    totals = SimpleNamespace(
        total=50, succeeded=45, total_cost=12.5,
        total_input=10000, total_output=5000, avg_duration=800.0,
    )
    db = StubDB(lambda *a, **kw: StubQuery(first_val=totals))
    with patch_session_and_models(
        db,
        patch("app.routers.insights._playbook_stats", return_value=[]),
    ):
        from app.tools.registrations.lens import get_analytics_summary
        out = get_analytics_summary(_CTX, days=30)
    assert out["total_runs"] == 50
    assert out["succeeded"] == 45
    assert out["failed"] == 5
    assert out["total_cost_usd"] == 12.5


def test_list_agent_status_shape_empty():
    """No workflows in workspace → empty rows, no join branches walked."""
    db = StubDB(lambda *a, **kw: StubQuery(rows=[]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import list_agent_status
        out = list_agent_status(_CTX)
    assert out == {"count": 0, "agents": []}


def test_get_playbook_scorecards_shape():
    row = SimpleNamespace(
        slug="autopilot_full", grade="A", pct=95.0,
        mechanical_score=95, mechanical_max=100,
        judge_score=90, judge_max=100, judge_used=True,
    )
    db = StubDB(lambda *a, **kw: StubQuery(rows=[row]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import get_playbook_scorecards
        out = get_playbook_scorecards(_CTX, days=30)
    assert out["count"] == 1
    assert out["scorecards"][0]["playbook_slug"] == "autopilot_full"
    assert out["scorecards"][0]["grade"] == "A"
    assert out["scorecards"][0]["grade_dist"]["A"] == 1
