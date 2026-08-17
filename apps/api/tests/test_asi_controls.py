"""Pure tests for the ASI control table. No DB, no FastAPI, no fixtures."""
from types import SimpleNamespace

from app.modules.guard.asi_controls import CONTROLS, evaluate


def _ctx(**overrides):
    base = dict(
        guard_active=False, fail_closed=False, signing_key=False,
        events_24h=0, chain_live=False, role_count=0,
        agent_identity_count=0, sessions_24h=0, guardrails_configured=False,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _status(ctx, asi):
    return {row[0]: row[3] for row in evaluate(ctx)}[asi]


def test_all_controls_returned_and_in_order():
    ids = [row[0] for row in evaluate(_ctx())]
    assert ids == [f"ASI-{i:02d}" for i in range(1, 11)]
    assert len(CONTROLS) == 10


def test_empty_workspace_grades_missing_or_partial():
    statuses = {row[0]: row[3] for row in evaluate(_ctx())}
    # nothing configured, guard not on -> everything either missing or partial (ASI-08 default)
    assert statuses["ASI-01"] == "missing"
    assert statuses["ASI-06"] == "missing"
    assert statuses["ASI-08"] == "partial"  # ASI-08 has no missing state, only active/partial
    assert statuses["ASI-09"] == "missing"


def test_asi06_requires_all_three_signals():
    # guard on but no events -> partial
    assert _status(_ctx(guard_active=True), "ASI-06") == "partial"
    # guard on + events but chain dead -> partial
    assert _status(_ctx(guard_active=True, events_24h=5), "ASI-06") == "partial"
    # all three -> active
    assert _status(_ctx(guard_active=True, events_24h=5, chain_live=True), "ASI-06") == "active"


def test_asi04_flips_on_role_count():
    assert _status(_ctx(guard_active=True), "ASI-04") == "partial"
    assert _status(_ctx(guard_active=True, role_count=1), "ASI-04") == "active"


def test_asi07_flips_on_agent_identity_count():
    assert _status(_ctx(guard_active=True), "ASI-07") == "partial"
    assert _status(_ctx(guard_active=True, agent_identity_count=1), "ASI-07") == "active"


def test_asi08_is_binary_active_or_partial():
    assert _status(_ctx(), "ASI-08") == "partial"
    assert _status(_ctx(fail_closed=True), "ASI-08") == "active"


def test_asi09_is_binary_active_or_missing():
    assert _status(_ctx(), "ASI-09") == "missing"
    assert _status(_ctx(signing_key=True), "ASI-09") == "active"


def test_asi10_flips_on_sessions_24h():
    assert _status(_ctx(guard_active=True), "ASI-10") == "partial"
    assert _status(_ctx(guard_active=True, sessions_24h=1), "ASI-10") == "active"


def test_asi03_flips_on_guardrails_configured():
    assert _status(_ctx(guard_active=True), "ASI-03") == "partial"
    assert _status(_ctx(guard_active=True, guardrails_configured=True), "ASI-03") == "active"
