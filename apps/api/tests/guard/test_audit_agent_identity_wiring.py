"""Phase 0 of #1959 — Gateway audit rows must carry agent_identity_id.

Before this fix, ``app.guard.audit.record`` had no ``agent_identity_id``
parameter and the raw INSERT statement omitted the column. The schema
column existed and was even indexed (models.py:230, 254), so every
Gateway audit row had a NULL identity for the entire life of the
column.

Regression: assert both the INSERT column list and the parameter
binding include the value we pass in.

The test uses a mocked session — enough to inspect the compiled SQL
without touching Postgres.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from app.guard.audit import record


AGENT_ID = "11111111-1111-1111-1111-111111111111"
WS_ID = "ef0a7e36-42a7-4968-9e6f-ee30d8e45383"


class _CapturingSession:
    """Session double that snapshots the last execute() call."""

    def __init__(self):
        self.last_sql: str | None = None
        self.last_params: dict | None = None

    def execute(self, stmt, params):
        # SQLAlchemy TextClause repr = the raw SQL string.
        self.last_sql = str(stmt)
        self.last_params = params
        return MagicMock()

    def commit(self):
        pass

    def close(self):
        pass


def _call(sess, **overrides):
    """Call record() with a minimal viable payload."""
    kwargs = {
        "workspace_id": WS_ID,
        "clerk_user_id": "user_abc",
        "ai_tool": "claude-code",
        "provider": "anthropic",
        "model": "claude-sonnet",
        "decision": "allowed",
        "rule_id": None,
        "duration_ms": 42,
        "body": {"messages": [{"role": "user", "content": "hi"}]},
        "response_bytes": None,
    }
    kwargs.update(overrides)
    with patch("app.guard.audit.SessionLocal", return_value=sess), \
         patch("app.guard.audit.set_workspace_rls"):
        record(**kwargs)


def test_agent_identity_id_appears_in_insert_column_list():
    sess = _CapturingSession()
    _call(sess, agent_identity_id=AGENT_ID)
    assert sess.last_sql is not None, "record() didn't execute an INSERT"
    # Column list — the schema has agent_identity_id, and #1959 Phase 0
    # asserts we actually write it.
    assert "agent_identity_id" in sess.last_sql


def test_agent_identity_id_parameter_binds_the_uuid_string():
    sess = _CapturingSession()
    _call(sess, agent_identity_id=AGENT_ID)
    assert sess.last_params is not None
    # The binding uses CAST(:agent_id AS uuid) so Postgres gets a real uuid.
    assert sess.last_params.get("agent_id") == AGENT_ID


def test_missing_agent_identity_id_still_writes_row_with_none():
    """Legacy callers without an identity (guard-mt-* member tokens,
    cedar-import, in-process one-off) must not crash. Row still lands;
    agent_id binding is None so Postgres stores NULL."""
    sess = _CapturingSession()
    _call(sess)  # no agent_identity_id
    assert sess.last_params.get("agent_id") is None
    assert "agent_identity_id" in sess.last_sql


def test_route_appears_in_insert_column_list():
    """Follow-up to #1971 — audit rows must carry the FastAPI request path
    so /proxy/* vs /gateway/v1/* is queryable directly."""
    sess = _CapturingSession()
    _call(sess, route="/gateway/v1/anthropic/v1/messages")
    assert sess.last_sql is not None
    assert "route" in sess.last_sql


def test_route_parameter_binds_the_path_string():
    sess = _CapturingSession()
    _call(sess, route="/gateway/v1/anthropic/v1/messages")
    assert sess.last_params.get("route") == "/gateway/v1/anthropic/v1/messages"


def test_missing_route_still_writes_row_with_none():
    """In-process callers (guard/gateway.py::guarded_*) have no HTTP route.
    They must not crash; route binding is None so Postgres stores NULL."""
    sess = _CapturingSession()
    _call(sess)  # no route
    assert sess.last_params.get("route") is None
    assert "route" in sess.last_sql


def test_metrics_counter_bumps_on_swallowed_exception():
    """When the INSERT raises, we must (a) not let the exception escape
    (per the docstring's 'never blocks the response' contract) and
    (b) bump GUARD_AUDIT_FAILED so ops can see the drop rate."""
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
    before = GUARD_AUDIT_FAILED.labels(reason="insert")._value.get()

    class _Blowup(_CapturingSession):
        def execute(self, stmt, params):
            raise RuntimeError("simulated DB blip")

    sess = _Blowup()
    _call(sess, agent_identity_id=AGENT_ID)   # must not raise

    after = GUARD_AUDIT_FAILED.labels(reason="insert")._value.get()
    assert after == before + 1, (
        f"GUARD_AUDIT_FAILED did not increment on swallowed exception "
        f"(before={before}, after={after})"
    )
