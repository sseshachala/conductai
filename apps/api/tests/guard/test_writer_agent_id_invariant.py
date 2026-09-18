"""PR-0.5b — writer-side agent_identity_id invariant.

Both audit writers in ``app/guard/audit.py`` (record + insert_accepted)
hardcode ``source='gateway'`` (post PR #2092). Auth is mandatory at
``/gateway/v1/*``, so every request reaching either writer should already
carry an ``agent_identity_id`` resolved from the bearer token.

These tests do NOT hit the DB — they patch ``SessionLocal`` and assert
the runtime observability fires (log warning + counter increment) when a
caller reaches the writer with ``agent_identity_id=None``. That path is a
leak we want to see in Prometheus before flipping the DB column to
NOT NULL in a follow-up.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _counter_value(counter, **labels) -> float:
    """Read a Prometheus Counter's current value for a label set."""
    return counter.labels(**labels)._value.get()


def test_record_bumps_counter_and_logs_when_agent_id_missing():
    from app.guard.audit import record
    from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID

    before = _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="record")

    warnings: list[dict] = []
    fake_log = MagicMock()
    fake_log.warning = lambda ev, **kw: warnings.append({"event": ev, **kw})

    with patch("app.guard.audit.log", fake_log), \
         patch("app.guard.audit.SessionLocal") as fake_session:
        # DB path is best-effort; make the session raise so the writer
        # short-circuits past the SQL. The invariant check runs BEFORE
        # SessionLocal(), so the counter fires regardless.
        fake_session.side_effect = RuntimeError("stubbed out")
        try:
            record(
                workspace_id="00000000-0000-0000-0000-000000000000",
                clerk_user_id=None,
                ai_tool="test-tool",
                provider="anthropic",
                model="claude-3-5-sonnet",
                decision="allowed",
                rule_id=None,
                duration_ms=1,
                body={"messages": [{"role": "user", "content": "hi"}]},
                response_bytes=None,
                agent_identity_id=None,
            )
        except RuntimeError:
            pass

    assert _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="record") == before + 1
    assert any(w["event"] == "guard.audit.missing_agent_identity_id" and w.get("writer") == "record" for w in warnings), warnings


def test_record_stays_silent_when_agent_id_present():
    from app.guard.audit import record
    from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID

    before = _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="record")

    warnings: list[dict] = []
    fake_log = MagicMock()
    fake_log.warning = lambda ev, **kw: warnings.append({"event": ev, **kw})

    with patch("app.guard.audit.log", fake_log), \
         patch("app.guard.audit.SessionLocal") as fake_session:
        fake_session.side_effect = RuntimeError("stubbed out")
        try:
            record(
                workspace_id="00000000-0000-0000-0000-000000000000",
                clerk_user_id=None,
                ai_tool="test-tool",
                provider="anthropic",
                model="claude-3-5-sonnet",
                decision="allowed",
                rule_id=None,
                duration_ms=1,
                body={"messages": [{"role": "user", "content": "hi"}]},
                response_bytes=None,
                agent_identity_id="agent-abc",
            )
        except RuntimeError:
            pass

    assert _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="record") == before
    assert not any(w["event"] == "guard.audit.missing_agent_identity_id" for w in warnings)


def test_insert_accepted_bumps_counter_and_logs_when_agent_id_missing():
    from app.guard.audit import insert_accepted
    from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID

    before = _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="insert_accepted")

    warnings: list[dict] = []
    fake_log = MagicMock()
    fake_log.warning = lambda ev, **kw: warnings.append({"event": ev, **kw})

    with patch("app.guard.audit.log", fake_log), \
         patch("app.guard.audit.SessionLocal") as fake_session:
        fake_session.side_effect = RuntimeError("stubbed out")
        try:
            insert_accepted(
                workspace_id="00000000-0000-0000-0000-000000000000",
                clerk_user_id=None,
                ai_tool="test-tool",
                provider="anthropic",
                model="claude-3-5-sonnet",
                request_id="11111111-1111-1111-1111-111111111111",
                body={"messages": [{"role": "user", "content": "hi"}]},
                agent_identity_id=None,
            )
        except RuntimeError:
            pass  # insert_accepted re-raises real failures; stub triggers this

    assert _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="insert_accepted") == before + 1
    assert any(w["event"] == "guard.audit.missing_agent_identity_id" and w.get("writer") == "insert_accepted" for w in warnings), warnings


def test_insert_accepted_stays_silent_when_agent_id_present():
    from app.guard.audit import insert_accepted
    from app.modules.guard.observability.metrics import GUARD_AUDIT_MISSING_AGENT_ID

    before = _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="insert_accepted")

    warnings: list[dict] = []
    fake_log = MagicMock()
    fake_log.warning = lambda ev, **kw: warnings.append({"event": ev, **kw})

    with patch("app.guard.audit.log", fake_log), \
         patch("app.guard.audit.SessionLocal") as fake_session:
        fake_session.side_effect = RuntimeError("stubbed out")
        try:
            insert_accepted(
                workspace_id="00000000-0000-0000-0000-000000000000",
                clerk_user_id=None,
                ai_tool="test-tool",
                provider="anthropic",
                model="claude-3-5-sonnet",
                request_id="11111111-1111-1111-1111-111111111111",
                body={"messages": [{"role": "user", "content": "hi"}]},
                agent_identity_id="agent-abc",
            )
        except RuntimeError:
            pass

    assert _counter_value(GUARD_AUDIT_MISSING_AGENT_ID, writer="insert_accepted") == before
    assert not any(w["event"] == "guard.audit.missing_agent_identity_id" for w in warnings)
