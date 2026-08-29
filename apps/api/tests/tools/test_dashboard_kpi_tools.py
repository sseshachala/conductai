"""Registration + shape parity for the #1439 batch — dashboard + observability
KPI tools registered under the free-function convention.

CI leaks MagicMock into SQLAlchemy Column attributes from earlier test
suites (see comment in test_batch_b_read_tools.py). We stub model classes
with `_FakeCol`-backed sentinels and call impls directly — dispatch wiring
is covered by the registration check.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # populate registry
from app.tools.registry import default_registry


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


# ── Model-column stubs (defeats CI's MagicMock leak on Column attrs) ─────────

class _FakeCol:
    def __eq__(self, _other): return "eq_expr"
    def __ge__(self, _other): return "ge_expr"
    def __gt__(self, _other): return "gt_expr"
    def __lt__(self, _other): return "lt_expr"
    def __le__(self, _other): return "le_expr"
    def __ne__(self, _other): return "ne_expr"
    def __add__(self, _other): return self
    def __radd__(self, _other): return self
    def in_(self, _other): return "in_expr"
    def isnot(self, _other): return "isnot_expr"
    def label(self, _name): return self
    def desc(self): return self
    def nullslast(self): return self


class _FakeRun:
    id = _FakeCol()
    workspace_id = _FakeCol()
    workflow_version_id = _FakeCol()
    status = _FakeCol()
    created_at = _FakeCol()
    locked_at = _FakeCol()


class _FakeWorkflow:
    id = _FakeCol()
    name = _FakeCol()
    workspace_id = _FakeCol()
    playbook_slug = _FakeCol()


class _FakeWorkflowVersion:
    id = _FakeCol()
    workflow_id = _FakeCol()


class _FakeRunTrace:
    run_id = _FakeCol()
    input_tokens = _FakeCol()
    output_tokens = _FakeCol()


class _FakeGuardAuditEvent:
    id = _FakeCol()
    workspace_id = _FakeCol()
    decision = _FakeCol()
    rule_id = _FakeCol()
    ts = _FakeCol()


class _FakeRunAnalyticsEvent:
    id = _FakeCol()
    run_id = _FakeCol()
    workspace_id = _FakeCol()
    created_at = _FakeCol()
    outcome = _FakeCol()
    cost_usd = _FakeCol()
    input_tokens = _FakeCol()
    output_tokens = _FakeCol()
    duration_ms = _FakeCol()
    trigger_type = _FakeCol()


class _FakeRunOnlineScore:
    slug = _FakeCol()
    grade = _FakeCol()
    pct = _FakeCol()
    mechanical_score = _FakeCol()
    mechanical_max = _FakeCol()
    judge_score = _FakeCol()
    judge_max = _FakeCol()
    judge_used = _FakeCol()
    run_id = _FakeCol()


# ── Query stub ──────────────────────────────────────────────────────────────

class _StubQuery:
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
    def distinct(self): return self
    def subquery(self): return self
    def all(self): return self._rows
    def count(self): return self._count
    def scalar(self): return self._scalar
    def first(self): return self._first


class _StubDB:
    def __init__(self, query_map=None):
        self._query_map = query_map or (lambda *a, **kw: _StubQuery())
    def query(self, *a, **kw): return self._query_map(*a, **kw)
    def close(self): pass


def _patch_common(stub_db):
    """Patch SessionLocal + all model classes used by the batch."""
    return [
        patch("app.core.database.SessionLocal", return_value=stub_db),
        patch("app.models.run.Run", _FakeRun),
        patch("app.models.workflow.Workflow", _FakeWorkflow),
        patch("app.models.workflow.WorkflowVersion", _FakeWorkflowVersion),
        patch("app.models.run_trace.RunTrace", _FakeRunTrace),
        patch("app.modules.guard.models.GuardAuditEvent", _FakeGuardAuditEvent),
        patch("app.models.run_analytics_event.RunAnalyticsEvent", _FakeRunAnalyticsEvent),
        patch("app.models.run_online_score.RunOnlineScore", _FakeRunOnlineScore),
    ]


def _enter(patches):
    for p in patches:
        p.start()


def _exit(patches):
    for p in patches:
        p.stop()


# ── Impl-shape tests ────────────────────────────────────────────────────────

def test_get_dashboard_outcomes_shape():
    fake_rows = [
        (SimpleNamespace(status="succeeded"), "autopilot_full"),
        (SimpleNamespace(status="failed"), "autopilot_full"),
    ]
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=fake_rows))
    patches = _patch_common(db) + [
        patch("app.routers.insights._outcome_type", return_value="pr_opened"),
    ]
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_dashboard_outcomes
        out = get_dashboard_outcomes(_CTX, time_window="last_7d")
    finally:
        _exit(patches)
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
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[(run, "wf-1", "Nightly")]))
    patches = _patch_common(db) + [
        patch("app.schemas.run._extract_trigger_summary", return_value="cron"),
        patch("app.routers.insights._extract_repo", return_value="acme/api"),
    ]
    _enter(patches)
    try:
        from app.tools.registrations.lens import list_attention_runs
        out = list_attention_runs(_CTX)
    finally:
        _exit(patches)
    assert out["count"] == 1
    assert out["runs"][0]["status"] == "failed"


def test_list_agent_health_shape_empty():
    """Empty aggregate — proves shape without hitting the last_run_status
    subquery path (which needs a real SQLAlchemy subquery)."""
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[]))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import list_agent_health
        out = list_agent_health(_CTX)
    finally:
        _exit(patches)
    assert out == {"count": 0, "agents": []}


def test_get_dashboard_token_usage_shape():
    row = SimpleNamespace(wf_id="wf-1", wf_name="A", input_tokens=1000, output_tokens=500)
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_dashboard_token_usage
        out = get_dashboard_token_usage(_CTX)
    finally:
        _exit(patches)
    assert out["total_input_tokens"] == 1000
    assert out["total_tokens"] == 1500
    assert len(out["by_agent"]) == 1


def test_get_top_policy_hits_shape():
    row = SimpleNamespace(rule_id="rule.no_prompt_injection", cnt=42)
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_top_policy_hits
        out = get_top_policy_hits(_CTX)
    finally:
        _exit(patches)
    assert out["hits"][0]["policy_name"] == "rule.no_prompt_injection"
    assert out["hits"][0]["count"] == 42


def test_get_observability_health_shape():
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[], count_val=0))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_observability_health
        out = get_observability_health(_CTX)
    finally:
        _exit(patches)
    for key in ("active_runs", "pending_approvals", "stale_workers",
                "succeeded_last_24h", "failed_last_24h", "total_last_24h",
                "error_rate_24h"):
        assert key in out


def test_get_dora_metrics_shape():
    totals = SimpleNamespace(total=100, succeeded=90, avg_duration=1234.0)
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[], first_val=totals))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_dora_metrics
        out = get_dora_metrics(_CTX, days=30)
    finally:
        _exit(patches)
    assert out["window_days"] == 30
    assert out["total_runs"] == 100
    assert out["deployment_frequency"] == round(90 / 30, 4)
    assert out["change_failure_rate"] == round(10 / 100, 4)


def test_get_analytics_summary_shape():
    totals = SimpleNamespace(
        total=50, succeeded=45, total_cost=12.5,
        total_input=10000, total_output=5000, avg_duration=800.0,
    )
    db = _StubDB(lambda *a, **kw: _StubQuery(first_val=totals))
    patches = _patch_common(db) + [
        patch("app.routers.insights._playbook_stats", return_value=[]),
    ]
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_analytics_summary
        out = get_analytics_summary(_CTX, days=30)
    finally:
        _exit(patches)
    assert out["total_runs"] == 50
    assert out["succeeded"] == 45
    assert out["failed"] == 5
    assert out["total_cost_usd"] == 12.5


def test_list_agent_status_shape_empty():
    """No workflows in workspace → empty rows, no join branches walked."""
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[]))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import list_agent_status
        out = list_agent_status(_CTX)
    finally:
        _exit(patches)
    assert out == {"count": 0, "agents": []}


def test_get_playbook_scorecards_shape():
    row = SimpleNamespace(
        slug="autopilot_full", grade="A", pct=95.0,
        mechanical_score=95, mechanical_max=100,
        judge_score=90, judge_max=100, judge_used=True,
    )
    db = _StubDB(lambda *a, **kw: _StubQuery(rows=[row]))
    patches = _patch_common(db)
    _enter(patches)
    try:
        from app.tools.registrations.lens import get_playbook_scorecards
        out = get_playbook_scorecards(_CTX, days=30)
    finally:
        _exit(patches)
    assert out["count"] == 1
    assert out["scorecards"][0]["playbook_slug"] == "autopilot_full"
    assert out["scorecards"][0]["grade"] == "A"
    assert out["scorecards"][0]["grade_dist"]["A"] == 1
