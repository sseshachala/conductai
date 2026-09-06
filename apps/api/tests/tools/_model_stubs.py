"""Shared model + query stubs for free-function Lens tool tests.

# Why this file exists

Free-function ToolDef tests (the #1281 / #1439 batches, and future ones)
that exercise the impl directly hit a known landmine: earlier test suites
in the same pytest process monkeypatch model modules
(`app.models.run.Run`, `app.modules.guard.models.GuardAuditEvent`, etc.)
and never restore them. By the time our tool test runs, `Run.created_at`
is a `MagicMock`, and `MagicMock >= datetime.now(...)` raises TypeError.

Local pytest often runs the failing test in isolation and passes — CI runs
the whole suite in order, so the leak lands.

# How to use

```python
from tests.tools._model_stubs import (
    FAKE_MODELS, StubDB, StubQuery, patch_session_and_models,
)

def test_my_tool_shape():
    db = StubDB(lambda *a, **kw: StubQuery(rows=[...]))
    with patch_session_and_models(db):
        from app.tools.registrations.lens import my_tool
        out = my_tool(_CTX)
    assert out["shape"] == "..."
```

`patch_session_and_models(db)` patches `SessionLocal` + every model class in
`FAKE_MODELS` in one shot. Extend `FAKE_MODELS` and add a new `_Fake*`
class here when your tool imports a model that isn't yet covered — do NOT
inline column stubs in individual tests.

# Rules

- Always call impls directly, not via `lens_dispatch`. Registration parity
  is covered by the batch's `test_*_registered` check; dispatch wiring is
  covered by the adapter's own tests.
- Every SQLAlchemy op used inside a tool (`>=`, `in_`, `label`, `desc`,
  `__add__`, etc.) needs a matching dunder on `FakeCol`. Add here when
  a new op shows up — do NOT extend inline.
"""
from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import patch


class FakeCol:
    """A stand-in for a SQLAlchemy Column attribute. Every operator returns
    a sentinel string (for filters) or self (for chained methods), so tool
    code that composes expressions runs to completion without a real DB."""
    def __eq__(self, _other): return "eq_expr"
    def __ne__(self, _other): return "ne_expr"
    def __ge__(self, _other): return "ge_expr"
    def __gt__(self, _other): return "gt_expr"
    def __le__(self, _other): return "le_expr"
    def __lt__(self, _other): return "lt_expr"
    def __add__(self, _other): return self
    def __radd__(self, _other): return self
    def __sub__(self, _other): return self
    def __mul__(self, _other): return self
    def in_(self, _other): return "in_expr"
    def isnot(self, _other): return "isnot_expr"
    def is_(self, _other): return "is_expr"
    def label(self, _name): return self
    def desc(self): return self
    def asc(self): return self
    def nullslast(self): return self
    def nullsfirst(self): return self
    def like(self, _other): return "like_expr"
    def ilike(self, _other): return "ilike_expr"


# ── Fake models — every attribute is a FakeCol so import-time column
# access + expression composition just works.

class FakeRun:
    id = FakeCol()
    workspace_id = FakeCol()
    workflow_version_id = FakeCol()
    status = FakeCol()
    created_at = FakeCol()
    started_at = FakeCol()
    locked_at = FakeCol()
    triggered_by = FakeCol()
    state = FakeCol()
    outcome = FakeCol()


class FakeWorkflow:
    id = FakeCol()
    name = FakeCol()
    workspace_id = FakeCol()
    playbook_slug = FakeCol()
    archived_at = FakeCol()
    is_template = FakeCol()
    updated_at = FakeCol()
    created_at = FakeCol()


class FakeWorkflowVersion:
    id = FakeCol()
    workflow_id = FakeCol()


class FakeRunTrace:
    run_id = FakeCol()
    input_tokens = FakeCol()
    output_tokens = FakeCol()


class FakeGuardAuditEvent:
    id = FakeCol()
    workspace_id = FakeCol()
    decision = FakeCol()
    rule_id = FakeCol()
    ts = FakeCol()
    cost_usd_after = FakeCol()
    cost_usd_before = FakeCol()
    tokens_before = FakeCol()
    tokens_after = FakeCol()
    agent_identity_id = FakeCol()
    clerk_user_id = FakeCol()
    session_id = FakeCol()
    conductai_workflow_id = FakeCol()
    user_email = FakeCol()


class FakeRunAnalyticsEvent:
    id = FakeCol()
    run_id = FakeCol()
    workspace_id = FakeCol()
    created_at = FakeCol()
    outcome = FakeCol()
    cost_usd = FakeCol()
    input_tokens = FakeCol()
    output_tokens = FakeCol()
    duration_ms = FakeCol()
    trigger_type = FakeCol()
    playbook_slug = FakeCol()
    model = FakeCol()


class FakeRunOnlineScore:
    slug = FakeCol()
    grade = FakeCol()
    pct = FakeCol()
    mechanical_score = FakeCol()
    mechanical_max = FakeCol()
    judge_score = FakeCol()
    judge_max = FakeCol()
    judge_used = FakeCol()
    run_id = FakeCol()


class FakeGuardSpendBudget:
    id = FakeCol()
    workspace_id = FakeCol()
    clerk_user_id = FakeCol()
    monthly_limit_usd = FakeCol()


class FakeWatchdogEvent:
    id = FakeCol()
    workspace_id = FakeCol()
    event_type = FakeCol()
    severity = FakeCol()
    run_id = FakeCol()
    workflow_id = FakeCol()
    payload = FakeCol()
    created_at = FakeCol()
    resolved_at = FakeCol()


# Map of (dotted patch target, fake class). Extend when a new model shows up.
#
# NOTE on tool-module local refs: lens/workflows.py and lens/runs.py hoist
# `from app.models.run import Run` (etc.) to module scope so a MagicMock
# leak in sys.modules[app.models.run] from other test files can't shadow
# the ORM class at tool-call time. patch("app.models.run.Run") alone won't
# reach those hoisted refs, so patch the tool-module names explicitly too.
FAKE_MODELS: list[tuple[str, type]] = [
    ("app.models.run.Run", FakeRun),
    ("app.models.workflow.Workflow", FakeWorkflow),
    ("app.models.workflow.WorkflowVersion", FakeWorkflowVersion),
    ("app.models.run_trace.RunTrace", FakeRunTrace),
    ("app.modules.guard.models.GuardAuditEvent", FakeGuardAuditEvent),
    ("app.modules.guard.models.GuardSpendBudget", FakeGuardSpendBudget),
    ("app.models.run_analytics_event.RunAnalyticsEvent", FakeRunAnalyticsEvent),
    ("app.models.run_online_score.RunOnlineScore", FakeRunOnlineScore),
    ("app.models.watchdog_event.WatchdogEvent", FakeWatchdogEvent),
    # Hoisted refs in lens tool modules — see NOTE above.
    ("app.tools.registrations.lens.workflows.Run", FakeRun),
    ("app.tools.registrations.lens.workflows.Workflow", FakeWorkflow),
    ("app.tools.registrations.lens.workflows.WorkflowVersion", FakeWorkflowVersion),
    ("app.tools.registrations.lens.runs.Run", FakeRun),
    ("app.tools.registrations.lens.runs.Workflow", FakeWorkflow),
    ("app.tools.registrations.lens.runs.WorkflowVersion", FakeWorkflowVersion),
]


class StubQuery:
    """Chainable query stub. Configure rows / count / scalar / first via the
    constructor; every builder method returns self."""
    def __init__(self, rows=None, count_val=0, scalar_val=0, first_val=None):
        self._rows = rows or []
        self._count = count_val
        self._scalar = scalar_val
        self._first = first_val
    def join(self, *a, **kw): return self
    def outerjoin(self, *a, **kw): return self
    def filter(self, *a, **kw): return self
    def filter_by(self, *a, **kw): return self
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
    def one(self): return self._first
    def one_or_none(self): return self._first


class StubDB:
    """Fake SQLAlchemy session. `query_map(*args, **kwargs)` receives the
    args passed to `db.query(...)` and returns a StubQuery."""
    def __init__(self, query_map=None):
        self._query_map = query_map or (lambda *a, **kw: StubQuery())
    def query(self, *a, **kw): return self._query_map(*a, **kw)
    def close(self): pass


@contextmanager
def patch_session_and_models(stub_db, *extra_patches):
    """One-shot: patches `app.core.database.SessionLocal` to return stub_db
    plus every entry in FAKE_MODELS. Extra `patch(...)` context managers
    (e.g. helpers imported from routers) can be passed positionally."""
    patches = [patch("app.core.database.SessionLocal", return_value=stub_db)]
    for target, cls in FAKE_MODELS:
        patches.append(patch(target, cls))
    patches.extend(extra_patches)
    for p in patches:
        p.start()
    try:
        yield
    finally:
        for p in patches:
            p.stop()
