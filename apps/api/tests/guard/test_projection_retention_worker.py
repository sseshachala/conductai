"""Guard projection-retention tests: retention worker pass + expiry backfill.

Split from ``test_projection_retention.py``; shared fake models and fixtures
live in ``_projection_retention_helpers.py``.
"""
from __future__ import annotations

from datetime import timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event, select

from app.modules.guard import projection_retention as retention
from app.modules.guard.projection_retention import (
    backfill_projection_expiry,
    cleanup_expired_projections,
    run_projection_retention_once,
)

from tests.guard._projection_retention_helpers import (  # noqa: F401 — fixtures
    MODELS,
    NOW,
    FakeAuditEvent,
    FakeIntent,
    FakeKnowledge,
    FakeSummary,
    _disable_rls_sql,
    _intent,
    _knowledge,
    _session,
    _session_factory,
)


def test_worker_log_callback_and_result_are_aggregate_only(monkeypatch):
    _, factory = _session_factory()
    with factory() as seed:
        _knowledge(seed, "private-workspace", "audit_event", NOW)
        seed.commit()
    callbacks = []
    logs = []
    created_sessions = []

    def tracked_factory():
        session = factory()
        created_sessions.append(session)
        return session

    class CapturingLog:
        def info(self, event, **values):
            logs.append((event, values))

    rls_calls = []
    monkeypatch.setattr(retention, "log", CapturingLog())
    monkeypatch.setattr(
        retention,
        "set_workspace_rls",
        lambda db, workspace_id: rls_calls.append((db, workspace_id)),
    )
    result = run_projection_retention_once(
        session_factory=tracked_factory,
        workspace_id="private-workspace",
        now=NOW,
        model_overrides=MODELS,
        settings_override=SimpleNamespace(guard_projection_prune_batch_size=7),
        on_result=callbacks.append,
    )

    assert result.knowledge_deleted == 0
    assert result.knowledge_orphans_deleted == 1
    assert result.batches_committed == 1
    assert len(created_sessions) == 4
    assert rls_calls == [
        (created_sessions[0], "private-workspace"),
        (created_sessions[1], "private-workspace"),
        (created_sessions[2], "private-workspace"),
        (created_sessions[3], "private-workspace"),
    ]
    assert all(not session.in_transaction() for session in created_sessions)
    assert callbacks == [result.to_dict()]
    assert logs == [("guard.projection_retention.completed", result.to_dict())]
    assert "workspace" not in repr(callbacks)
    assert "private-workspace" not in repr(callbacks)
    assert "private-workspace" not in repr(logs)


def test_worker_rejects_legacy_caller_session():
    session = _session()

    with pytest.raises(ValueError, match="does not accept a caller-owned db session"):
        run_projection_retention_once(session, now=NOW, model_overrides=MODELS)


def test_worker_commits_knowledge_before_later_intent_failure(monkeypatch):
    _, factory = _session_factory()
    with factory() as seed:
        knowledge = _knowledge(seed, "ws-a", "audit_event", NOW)
        intent = _intent(seed, "ws-a", "pending", NOW)
        seed.commit()
        knowledge_id = knowledge.id
        intent_id = intent.id
    created_sessions = []

    def tracked_factory():
        session = factory()
        created_sessions.append(session)
        return session

    def fail_intent_batch(*args, **kwargs):
        raise RuntimeError("forced intent failure")

    monkeypatch.setattr(retention, "_expire_intent_batch", fail_intent_batch)

    with pytest.raises(RuntimeError, match="forced intent failure"):
        run_projection_retention_once(
            session_factory=tracked_factory,
            workspace_id="ws-a",
            now=NOW,
            model_overrides=MODELS,
        )

    assert len(created_sessions) == 3
    assert all(not session.in_transaction() for session in created_sessions)
    with factory() as verifier:
        assert verifier.get(FakeKnowledge, knowledge_id) is None
        assert verifier.get(FakeIntent, intent_id).status == "pending"


@pytest.mark.parametrize("dry_run", [True, False])
def test_worker_dry_run_and_empty_pass_release_connection_and_transaction(dry_run):
    engine, factory = _session_factory()
    checkouts = 0
    checkins = 0
    created_sessions = []

    @event.listens_for(engine, "checkout")
    def track_checkout(*args):
        nonlocal checkouts
        checkouts += 1

    @event.listens_for(engine, "checkin")
    def track_checkin(*args):
        nonlocal checkins
        checkins += 1

    def tracked_factory():
        session = factory()
        created_sessions.append(session)
        return session

    result = run_projection_retention_once(
        session_factory=tracked_factory,
        workspace_id="ws-a",
        dry_run=dry_run,
        now=NOW,
        model_overrides=MODELS,
    )

    assert result.knowledge_deleted == result.intents_expired == 0
    assert checkouts == checkins
    assert checkouts == (1 if dry_run else 4)
    assert len(created_sessions) == (1 if dry_run else 4)
    assert all(not session.in_transaction() for session in created_sessions)


def test_backfill_uses_source_time_exact_cutoff_and_preserves_rules():
    session = _session()
    event_source = FakeAuditEvent(workspace_id='ws-a', ts=NOW - timedelta(days=30))
    session.add(event_source)
    session.flush()
    event_projection = _knowledge(session, 'ws-a', 'audit_event', None, updated_at=NOW)
    event_projection.source_id = str(event_source.id)
    rule = _knowledge(session, 'ws-a', 'rule', None, updated_at=NOW)
    other = _knowledge(session, 'ws-b', 'audit_event', None, updated_at=NOW)
    other.source_id = str(event_source.id)
    session.commit()

    result = backfill_projection_expiry(
        session,
        workspace_id='ws-a',
        retention_days=30,
        model_overrides=MODELS,
    )
    session.commit()
    session.refresh(event_projection)

    assert result.knowledge_backfilled == 1
    assert event_projection.source_timestamp.replace(tzinfo=timezone.utc) == event_source.ts.replace(tzinfo=timezone.utc)
    assert event_projection.expires_at.replace(tzinfo=timezone.utc) == NOW
    assert rule.expires_at is None
    assert other.expires_at is None

    cleanup = cleanup_expired_projections(
        session,
        workspace_id='ws-a',
        now=NOW,
        model_overrides={'knowledge': FakeKnowledge},
    )
    session.commit()
    assert cleanup.knowledge_deleted == 1
    assert session.get(FakeKnowledge, rule.id) is not None
    assert session.get(FakeKnowledge, other.id) is not None


def test_backfill_summary_metadata_orphans_and_multiple_batches_converge():
    session = _session()
    summary = FakeSummary(
        workspace_id='ws-a',
        window_end=NOW - timedelta(days=2),
        source_timestamp=NOW - timedelta(days=2),
        expires_at=NOW + timedelta(days=28),
    )
    session.add(summary)
    session.flush()
    summary_projection = _knowledge(session, 'ws-a', 'audit_summary', None)
    summary_projection.source_id = str(summary.id)
    event_one = FakeAuditEvent(workspace_id='ws-a', ts=NOW - timedelta(days=1))
    event_two = FakeAuditEvent(workspace_id='ws-a', ts=NOW - timedelta(days=3))
    session.add_all([event_one, event_two])
    session.flush()
    for source in (event_one, event_two):
        row = _knowledge(session, 'ws-a', 'audit_event', None)
        row.source_id = str(source.id)
    orphan = _knowledge(session, 'ws-a', 'audit_event', None)
    orphan.source_id = '999999'
    session.commit()

    dry = backfill_projection_expiry(
        session,
        workspace_id='ws-a',
        retention_days=30,
        batch_size=2,
        dry_run=True,
        model_overrides=MODELS,
    )
    assert dry.backfill_candidates == 4

    totals = {'backfilled': 0, 'orphans': 0}
    for _ in range(3):
        result = backfill_projection_expiry(
            session,
            workspace_id='ws-a',
            retention_days=30,
            batch_size=2,
            model_overrides=MODELS,
        )
        totals['backfilled'] += result.knowledge_backfilled
        totals['orphans'] += result.knowledge_orphans_deleted
        session.commit()

    session.refresh(summary_projection)
    assert summary_projection.source_timestamp.replace(tzinfo=timezone.utc) == summary.source_timestamp.replace(tzinfo=timezone.utc)
    assert summary_projection.expires_at.replace(tzinfo=timezone.utc) == summary.expires_at.replace(tzinfo=timezone.utc)
    assert totals == {'backfilled': 3, 'orphans': 1}
    assert session.scalar(
        select(retention.func.count()).select_from(FakeKnowledge).where(
            FakeKnowledge.workspace_id == 'ws-a',
            FakeKnowledge.source_kind.in_(('audit_event', 'audit_summary')),
            retention.or_(FakeKnowledge.source_timestamp.is_(None), FakeKnowledge.expires_at.is_(None)),
        )
    ) == 0
