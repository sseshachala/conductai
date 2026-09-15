"""Phase 1 of #1959 — durable inference audit primitives.

Regression harness for the two-phase writer landed in
`app.guard.audit`:

    insert_accepted() → lifecycle_state='accepted'  (pre-inference)
    finalize()        → lifecycle_state='finalized' (post-inference)

Uses a mocked SessionLocal — enough to inspect the compiled SQL and
verify state transitions without touching Postgres. The migration and
model land in the same PR; the schema drift regression test that runs
against a real DB in CI covers the actual column shape.
"""
from __future__ import annotations

from unittest.mock import patch, MagicMock

from app.guard.audit import finalize, insert_accepted


WS_ID = "ef0a7e36-42a7-4968-9e6f-ee30d8e45383"
REQUEST_ID = "cccccccc-cccc-cccc-cccc-cccccccccccc"
AGENT_ID = "11111111-1111-1111-1111-111111111111"


class _CapturingSession:
    """Session double that snapshots the last execute() call.

    ``rowcount_for`` lets finalize() tests configure whether the mock
    UPDATE matched a row so we can exercise both the happy path and the
    "row missing / already finalized" branch.
    """

    def __init__(self, rowcount_for_update: int = 1):
        self.last_sql: str | None = None
        self.last_params: dict | None = None
        self._rowcount = rowcount_for_update
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def execute(self, stmt, params):
        self.last_sql = str(stmt)
        self.last_params = params
        result = MagicMock()
        result.rowcount = self._rowcount
        return result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _patch_session(sess):
    return (
        patch("app.guard.audit.SessionLocal", return_value=sess),
        patch("app.guard.audit.set_workspace_rls"),
    )


# ─── insert_accepted() ────────────────────────────────────────────────────────


def _insert(sess, **overrides):
    kwargs = {
        "workspace_id": WS_ID,
        "clerk_user_id": "user_abc",
        "ai_tool": "claude-code",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "request_id": REQUEST_ID,
        "body": {"messages": [{"role": "user", "content": "hi"}]},
    }
    kwargs.update(overrides)
    p1, p2 = _patch_session(sess)
    with p1, p2:
        return insert_accepted(**kwargs)


def test_insert_accepted_writes_row_with_accepted_lifecycle_state():
    sess = _CapturingSession()
    _insert(sess)
    assert sess.last_sql is not None
    assert "'accepted'" in sess.last_sql
    assert "lifecycle_state" in sess.last_sql
    assert "accepted_at" in sess.last_sql
    assert "lease_expires_at" in sess.last_sql


def test_insert_accepted_binds_request_id():
    sess = _CapturingSession()
    _insert(sess)
    assert sess.last_params is not None
    assert sess.last_params.get("request_id") == REQUEST_ID


def test_insert_accepted_returns_row_id():
    sess = _CapturingSession()
    row_id = _insert(sess)
    assert isinstance(row_id, str)
    # Bound to the same string used in the INSERT so a follow-up
    # finalize(row_id) targets the correct row.
    assert sess.last_params.get("row_id") == row_id


def test_insert_accepted_uses_receipt_id_when_provided():
    """Pre-minted receipt id lets the caller respond to the client with a
    receipt URL before the row is written — same pattern record() uses."""
    sess = _CapturingSession()
    preminted = "44444444-4444-4444-4444-444444444444"
    row_id = _insert(sess, receipt_id=preminted)
    assert row_id == preminted
    assert sess.last_params.get("row_id") == preminted


def test_insert_accepted_sets_lease_expires_at_relative_to_accepted_at():
    """lease_expires_at must be exactly lease_seconds after accepted_at so
    the reconciler in Phase 4 can compute expiry deterministically."""
    sess = _CapturingSession()
    _insert(sess, lease_seconds=90)
    accepted_at = sess.last_params["accepted_at"]
    lease_expires_at = sess.last_params["lease_expires_at"]
    delta = (lease_expires_at - accepted_at).total_seconds()
    assert delta == 90


def test_insert_accepted_commits_on_success():
    sess = _CapturingSession()
    _insert(sess)
    assert sess.committed is True
    assert sess.rolled_back is False
    assert sess.closed is True


def test_insert_accepted_rolls_back_on_failure():
    class _Blowup(_CapturingSession):
        def execute(self, stmt, params):
            raise RuntimeError("simulated integrity error")

    sess = _Blowup()
    import pytest

    with pytest.raises(RuntimeError):
        _insert(sess)
    assert sess.rolled_back is True
    assert sess.committed is False
    assert sess.closed is True


def test_insert_accepted_threads_agent_identity_id():
    """Phase 0 attribution stays intact when the durable writer is on."""
    sess = _CapturingSession()
    _insert(sess, agent_identity_id=AGENT_ID)
    assert sess.last_params.get("agent_id") == AGENT_ID


def test_insert_accepted_threads_route():
    """Phase 1 rows must still carry the FastAPI request path so the
    /proxy/* vs /gateway/v1/* signal from #1973 keeps working."""
    sess = _CapturingSession()
    _insert(sess, route="/gateway/v1/anthropic/v1/messages")
    assert sess.last_params.get("route") == "/gateway/v1/anthropic/v1/messages"


# ─── finalize() ───────────────────────────────────────────────────────────────


def _finalize(sess, **overrides):
    kwargs = {
        "row_id": "22222222-2222-2222-2222-222222222222",
        "workspace_id": WS_ID,
        "decision": "allowed",
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
        "body": {"messages": [{"role": "user", "content": "hi"}]},
        "response_bytes": b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        "duration_ms": 123,
    }
    kwargs.update(overrides)
    p1, p2 = _patch_session(sess)
    with p1, p2:
        return finalize(**kwargs)


def test_finalize_flips_lifecycle_state_to_finalized():
    sess = _CapturingSession(rowcount_for_update=1)
    ok = _finalize(sess)
    assert ok is True
    assert "'finalized'" in sess.last_sql
    assert "finalized_at" in sess.last_sql


def test_finalize_only_updates_rows_still_in_accepted():
    """The UPDATE's WHERE clause guarantees we never regress a finalized
    row or clobber an orphaned one — this is the invariant Phase 4's
    reconciler relies on."""
    sess = _CapturingSession()
    _finalize(sess)
    assert "lifecycle_state = 'accepted'" in sess.last_sql


def test_finalize_returns_false_when_no_row_matched():
    """rowcount=0 means the row wasn't in 'accepted' state — either the
    id is unknown or it was already finalized/orphaned/expired. Caller
    can treat this as "someone else finalized it first" and continue."""
    sess = _CapturingSession(rowcount_for_update=0)
    ok = _finalize(sess)
    assert ok is False


def test_finalize_persists_the_real_decision():
    """The 'accepted' placeholder decision from insert_accepted() must be
    overwritten with the outcome the policy engine produced."""
    sess = _CapturingSession()
    _finalize(sess, decision="blocked", rule_id="proxy-no-credential-leak")
    assert sess.last_params.get("decision") == "blocked"
    assert sess.last_params.get("rule_id") == "proxy-no-credential-leak"


def test_finalize_parses_token_counts_from_response():
    sess = _CapturingSession()
    _finalize(sess)
    # Anthropic usage shape: {"input_tokens": ..., "output_tokens": ...}
    assert sess.last_params.get("tin") == 10
    assert sess.last_params.get("tout") == 5


def test_finalize_commits_on_success():
    sess = _CapturingSession()
    _finalize(sess)
    assert sess.committed is True
    assert sess.rolled_back is False
    assert sess.closed is True


def test_finalize_rolls_back_on_failure():
    class _Blowup(_CapturingSession):
        def execute(self, stmt, params):
            raise RuntimeError("simulated timeout")

    sess = _Blowup()
    import pytest

    with pytest.raises(RuntimeError):
        _finalize(sess)
    assert sess.rolled_back is True
    assert sess.committed is False
    assert sess.closed is True


def test_finalize_binds_row_id_as_target():
    sess = _CapturingSession()
    row_id = "77777777-7777-7777-7777-777777777777"
    _finalize(sess, row_id=row_id)
    assert sess.last_params.get("row_id") == row_id



# ─── Phase 2: expanded field coverage ─────────────────────────────────────────


def test_insert_accepted_threads_share_token_hash():
    """Trial workspace blocks mint a share token whose sha256 goes on the
    accepted row so the anonymous receipt endpoint can authenticate."""
    sess = _CapturingSession()
    _insert(sess, share_token_hash="deadbeef" * 8)
    assert sess.last_params.get("share_token_hash") == "deadbeef" * 8


def test_insert_accepted_threads_conductai_workflow_metadata():
    """Workflow-driven proxy calls carry run_id + workflow + workflow_id so
    the Flight Recorder in Phase 3 can link an audit row back to a run."""
    sess = _CapturingSession()
    _insert(
        sess,
        conductai_run_id="run_abc",
        conductai_workflow="triage-pipeline",
        conductai_workflow_id="wf_def",
    )
    assert sess.last_params.get("run_id") == "run_abc"
    assert sess.last_params.get("workflow") == "triage-pipeline"
    assert sess.last_params.get("workflow_id") == "wf_def"


def test_insert_accepted_threads_blast_radius():
    """Hook events pass blast_radius (JSON dict); insert_accepted must
    persist it as jsonb, not str."""
    sess = _CapturingSession()
    _insert(sess, blast_radius={"tool": "bash", "cwd": "/tmp"})
    import json as _json
    assert _json.loads(sess.last_params["blast_radius"]) == {"tool": "bash", "cwd": "/tmp"}


def test_finalize_persists_evaluated_rules_and_defense_score():
    """Layered verdict envelope (#1150) must survive the accepted->finalized
    UPDATE. The COALESCE guards let a caller update evaluated_rules
    without wiping a value the accepted row already carried."""
    sess = _CapturingSession()
    _finalize(
        sess,
        evaluated_rules=[{"rule_id": "no-creds", "severity": "critical", "action": "block"}],
        defense_score=80,
    )
    import json as _json
    assert sess.last_params.get("score") == 80
    parsed = _json.loads(sess.last_params["eval"])
    assert parsed[0]["rule_id"] == "no-creds"


def test_finalize_persists_rule_message():
    sess = _CapturingSession()
    _finalize(sess, rule_message="Credential detected in prompt.")
    assert sess.last_params.get("rule_message") == "Credential detected in prompt."


def test_finalize_calls_notify_guard_block_on_blocked_decision():
    """Phase 1 self-review gap #2 — record() fires the Slack notifier when
    it writes a block; finalize() must mirror that or block-worthy
    durable-path calls go silent in Slack."""
    from unittest.mock import MagicMock
    sess = _CapturingSession(rowcount_for_update=1)
    _notifier = MagicMock()

    import app.modules.guard.routers.events as _events_mod
    with patch.object(_events_mod, "notify_guard_block", _notifier):
        _finalize(sess, decision="blocked", rule_id="proxy-no-credential-leak")

    assert _notifier.called
    kw = _notifier.call_args.kwargs
    assert kw["decision"] == "blocked"
    assert kw["rule_id"] == "proxy-no-credential-leak"
    assert kw["source"] == "proxy"


def test_finalize_does_not_notify_when_no_row_matched():
    """If the UPDATE returned rowcount=0 the row was already finalized or
    is gone — firing Slack in that case would double-alert. Skip."""
    from unittest.mock import MagicMock
    sess = _CapturingSession(rowcount_for_update=0)
    _notifier = MagicMock()
    import app.modules.guard.routers.events as _events_mod
    with patch.object(_events_mod, "notify_guard_block", _notifier):
        _finalize(sess, decision="blocked", rule_id="proxy-no-credential-leak")
    assert not _notifier.called


def test_finalize_does_not_notify_for_allowed_decisions():
    from unittest.mock import MagicMock
    sess = _CapturingSession()
    _notifier = MagicMock()
    import app.modules.guard.routers.events as _events_mod
    with patch.object(_events_mod, "notify_guard_block", _notifier):
        _finalize(sess, decision="allowed")
    assert not _notifier.called


# ─── Phase 2: _schedule_audit dispatcher ──────────────────────────────────────


def test_schedule_audit_calls_finalize_when_durable_id_present():
    """audit_args[18] is the durable row id. When set, _schedule_audit
    routes to finalize() and never calls record()."""
    from fastapi import BackgroundTasks
    from unittest.mock import MagicMock, patch as _patch
    from app.guard.router import _schedule_audit

    bg = BackgroundTasks()
    audit_args = (
        WS_ID, "user_abc", "claude-code", "anthropic", "claude-sonnet",
        "allowed", None, 12345.0, {"messages": []},
        "prompt", "user@example.com", None, None, None, None, None,
        AGENT_ID, "/proxy/anthropic/v1/messages",
        "22222222-2222-2222-2222-222222222222",  # durable row id
    )
    fake_finalize = MagicMock()
    fake_record = MagicMock()
    with _patch("app.guard.router._finalize_audit", fake_finalize), \
         _patch("app.guard.router._record_audit", fake_record):
        _schedule_audit(bg, audit_args, response_bytes=b"{}", upstream=None)
    for task in bg.tasks:
        task.func(*task.args, **task.kwargs)
    assert fake_finalize.called
    assert not fake_record.called
    assert fake_finalize.call_args.args[0] == "22222222-2222-2222-2222-222222222222"


def test_schedule_audit_calls_record_when_no_durable_id():
    """Single-phase remains the default: without audit_args[18] we still go
    through record() so the flag-off code path is unchanged."""
    from fastapi import BackgroundTasks
    from unittest.mock import MagicMock, patch as _patch
    from app.guard.router import _schedule_audit

    bg = BackgroundTasks()
    audit_args = (
        WS_ID, "user_abc", "claude-code", "anthropic", "claude-sonnet",
        "allowed", None, 12345.0, {"messages": []},
        "prompt", "user@example.com", None, None, None, None, None,
        AGENT_ID, "/proxy/anthropic/v1/messages",
    )
    fake_finalize = MagicMock()
    fake_record = MagicMock()
    with _patch("app.guard.router._finalize_audit", fake_finalize), \
         _patch("app.guard.router._record_audit", fake_record):
        _schedule_audit(bg, audit_args, response_bytes=b"{}", upstream=None)
    for task in bg.tasks:
        task.func(*task.args, **task.kwargs)
    assert fake_record.called
    assert not fake_finalize.called


# ─── Post-P1 Finding 2: late_finalize observability ─────────────────────


def test_late_finalize_bumps_anomaly_counter_and_logs():
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
    before = GUARD_AUDIT_FAILED.labels(reason="late_finalize")._value.get()
    sess = _CapturingSession(rowcount_for_update=0)
    ok = _finalize(sess, decision="allowed")
    assert ok is False
    after = GUARD_AUDIT_FAILED.labels(reason="late_finalize")._value.get()
    assert after == before + 1


# ─── Post-P1 Finding 2: renew_lease heartbeat ───────────────────────────


def test_renew_lease_extends_the_expiration_when_row_is_accepted():
    from app.guard.audit import renew_lease
    sess = _CapturingSession(rowcount_for_update=1)
    p1, p2 = _patch_session(sess)
    with p1, p2:
        ok = renew_lease("22222222-2222-2222-2222-222222222222", WS_ID, additional_seconds=180)
    assert ok is True
    assert "UPDATE guard_audit_events" in sess.last_sql
    assert "lease_expires_at" in sess.last_sql
    assert "lifecycle_state = 'accepted'" in sess.last_sql


def test_renew_lease_returns_false_when_row_no_longer_accepted():
    from app.guard.audit import renew_lease
    sess = _CapturingSession(rowcount_for_update=0)
    p1, p2 = _patch_session(sess)
    with p1, p2:
        assert renew_lease("id", WS_ID, additional_seconds=60) is False
