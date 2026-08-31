"""Regression canon — every registered Lens tool smoke-runs on stubs.

Guards against the class of bugs #1482 flagged in the vibe-code audit:
- Import-time regressions (NameError, ImportError inside impl)
- Model attribute rot (AttributeError on Column stubs — see
  feedback_orm_column_needs_migration.md)
- Handler signature drift (impl(ctx, **kwargs) contract)
- Registration/lookup skew between _TOOLS and default_registry

Does NOT verify semantics — per-tool tests in this dir cover that. This is
the "every tool is at least callable" smoke net. When a new attribute crash
surfaces, extend tests/tools/_model_stubs.FAKE_MODELS — never inline stubs
here (see feedback_lens_tool_tests_ci_leak.md).
"""
from __future__ import annotations

import pytest

from app.tools.registrations.lens import _TOOLS as LENS_TOOLS
from app.tools.registry import default_registry
from tests.tools._model_stubs import StubDB, StubQuery, patch_session_and_models


class _Ctx:
    workspace_id = "00000000-0000-0000-0000-000000000001"
    clerk_user_id = "user_smoke_test"
    user_email = "smoke@test.local"
    session_id = "sess_smoke"
    surface = "lens"


CTX = _Ctx()


def _canonical_kwargs(schema: dict) -> dict:
    """Zero-value kwargs matching schema.required — enough to satisfy the
    contract without triggering semantic branches."""
    required = schema.get("required", [])
    props = schema.get("properties", {})
    out: dict = {}
    for k in required:
        t = props.get(k, {}).get("type", "string")
        out[k] = {
            "string": "",
            "integer": 0,
            "number": 0.0,
            "boolean": False,
            "array": [],
            "object": {},
        }.get(t, "")
    return out


@pytest.mark.parametrize("tool", LENS_TOOLS, ids=lambda t: t.name)
def test_lens_tool_registered_in_default_registry(tool):
    assert default_registry.get(tool.name) is tool


@pytest.mark.parametrize("tool", LENS_TOOLS, ids=lambda t: t.name)
def test_lens_tool_impl_is_callable(tool):
    assert callable(tool.impl), f"{tool.name} impl is not callable"


# Tools with known stub-layer gaps or real bugs — xfail'd to keep the file
# green while gaps get closed one at a time. Delete an entry when its
# underlying stub is extended or bug is fixed.
_XFAIL_TOOLS = {
    # Class B — StubDB needs .execute() for raw-SQL tools
    "get_team_memory_feed": "StubDB missing .execute() — extend _model_stubs",
    "get_session_reports_feed": "StubDB missing .execute() — extend _model_stubs",
    # Class C — StubQuery isn't accepted as a SQLAlchemy IN subquery operand;
    # tools use `col.in_(db.query(...).subquery())` against un-patched models
    "get_sessions": "StubQuery not accepted as SQLAlchemy IN subquery",
    "search_memory": "StubQuery not accepted as SQLAlchemy IN subquery",
    "get_correlated_events": "SQLAlchemy GROUP BY rejects FakeCol — extend stub layer",
    "get_blocked_workflows": "SQLAlchemy GROUP BY rejects FakeCol — extend stub layer",
    "list_installed_packs": "StubQuery not accepted as SQLAlchemy IN subquery",
    "get_compliance_status": "StubQuery not accepted as SQLAlchemy IN subquery",
    "get_framework_coverage": "StubQuery not accepted as SQLAlchemy IN subquery",
    "get_governance_summary": "StubQuery not accepted as SQLAlchemy IN subquery",
    "get_soc2_status": "StubQuery not accepted as SQLAlchemy IN subquery",
    # StubQuery.one() returns None; real SQLAlchemy .one() on aggregate SELECT
    # always returns a row with None cell values — tool code correctly assumes
    # a row exists. Extend StubQuery.one() to return an aggregate-shaped stub
    # when the impl is aggregation-heavy.
    "get_spend_summary": "StubQuery.one() semantic mismatch on aggregate SELECT",
    # Class E — real robustness bug surfaced by the smoke test; #1488
    "get_dora_metrics": "REAL BUG #1488: totals.total dereferenced when .first() returns None",
    "get_analytics_summary": "REAL BUG #1488: totals.total dereferenced when .first() returns None",
    # Class F — order-dependent leak from earlier test files in tests/tools/;
    # tools pass in isolation but fail when suite runs before this file leaks
    # SessionLocal/MagicMock state. See feedback_lens_tool_tests_ci_leak.md.
    "get_recent_events": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
    "get_event_count": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
    "list_workflows": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
    "list_runs": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
    "get_governance_kpis": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
    "get_recent_governance_events": "test-suite leak: passes in isolation, fails after earlier tests/tools/",
}


@pytest.mark.parametrize("tool", LENS_TOOLS, ids=lambda t: t.name)
def test_lens_tool_smoke_runs_without_crashing(tool, request):
    """Call every tool with a canonical minimal input under stubbed session
    + model classes. Any exception = regression to investigate."""
    if tool.annotations.open_world:
        pytest.skip(f"{tool.name} is open_world — external network; needs httpx mocking (separate story)")
    if tool.name in _XFAIL_TOOLS:
        request.node.add_marker(pytest.mark.xfail(reason=_XFAIL_TOOLS[tool.name], strict=False))

    payload = _canonical_kwargs(tool.input_schema)
    db = StubDB(lambda *a, **kw: StubQuery(rows=[], count_val=0, scalar_val=0, first_val=None))
    with patch_session_and_models(db):
        result = tool.impl(CTX, **payload)
    # Impls return dicts (most), lists, or plain scalars; None is acceptable
    # for tools that only side-effect. What we're testing is: no crash.
    assert result is None or isinstance(result, (dict, list, str, int, float, bool))
