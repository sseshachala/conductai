from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.modules.guard import projection_retention as retention
from app.modules.guard.projection_retention import (
    active_projection_sql_predicate,
    cleanup_expired_projections,
    filter_active_projections,
)

from tests.guard._projection_retention_helpers import (  # noqa: F401 — fixtures
    MODELS,
    NOW,
    FakeGuardAuditEvent,
    FakeIntent,
    FakeIntentWithoutSourceKind,
    FakeKnowledge,
    FakeSummary,
    _disable_rls_sql,
    _intent,
    _knowledge,
    _session,
    _session_factory,
    _summary,
)


def test_search_filter_is_workspace_scoped_and_excludes_exact_cutoff():
    session = _session()
    _knowledge(session, "ws-a", "audit_event", None)
    _knowledge(session, "ws-a", "audit_event", NOW + timedelta(microseconds=1))
    _knowledge(session, "ws-a", "audit_event", NOW)
    _knowledge(session, "ws-b", "audit_event", None)
    session.commit()

    statement = filter_active_projections(
        select(FakeKnowledge), model=FakeKnowledge, workspace_id="ws-a", now=NOW
    )
    rows = session.execute(statement.order_by(FakeKnowledge.id)).scalars().all()

    assert [(row.workspace_id, row.expires_at) for row in rows] == [
        ("ws-a", None),
        ("ws-a", (NOW + timedelta(microseconds=1)).replace(tzinfo=None)),
    ]


@pytest.mark.parametrize("workspace_id", [None, "", "   "])
def test_search_filter_rejects_missing_or_blank_workspace_id(workspace_id):
    with pytest.raises(ValueError, match="workspace_id is required"):
        filter_active_projections(
            select(FakeKnowledge),
            model=FakeKnowledge,
            workspace_id=workspace_id,
            now=NOW,
        )


def test_raw_sql_predicate_combines_workspace_and_expiry_scope():
    assert active_projection_sql_predicate(
        "gki", workspace_param="workspace_id", now_param="search_now"
    ) == (
        "gki.workspace_id = CAST(:workspace_id AS uuid) "
        "AND (gki.expires_at IS NULL OR gki.expires_at > :search_now)"
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("alias", "gki; DROP TABLE guard_knowledge_index"),
        ("alias", "gki.expires_at"),
        ("workspace_param", "workspace-id"),
        ("now_param", "now) OR TRUE --"),
    ],
)
def test_raw_sql_predicate_rejects_unsafe_identifiers(field, value):
    values = {
        "alias": "gki",
        "workspace_param": "workspace_id",
        "now_param": "projection_now",
    }
    values[field] = value

    with pytest.raises(ValueError, match=f"{field} must be a safe SQL identifier"):
        active_projection_sql_predicate(**values)


def test_cleanup_exact_cutoff_preserves_other_sources_and_tenants():
    session = _session()
    exact = _knowledge(session, "ws-a", "audit_event", NOW)
    summary = _knowledge(session, "ws-a", "audit_summary", NOW - timedelta(days=1))
    future = _knowledge(session, "ws-a", "audit_event", NOW + timedelta(seconds=1))
    no_expiry = _knowledge(session, "ws-a", "audit_event", None)
    rule = _knowledge(session, "ws-a", "rule", NOW - timedelta(days=1))
    agent = _knowledge(session, "ws-a", "discovered_agent", NOW - timedelta(days=1))
    other = _knowledge(session, "ws-b", "audit_event", NOW - timedelta(days=1))
    raw_audit = FakeGuardAuditEvent(workspace_id="ws-a", expires_at=NOW)
    session.add(raw_audit)
    session.commit()
    deleted_ids = {exact.id, summary.id}
    preserved_ids = {future.id, no_expiry.id, rule.id, agent.id, other.id}

    result = cleanup_expired_projections(
        session, workspace_id="ws-a", now=NOW, model_overrides=MODELS
    )
    session.commit()

    remaining = {row.id for row in session.scalars(select(FakeKnowledge))}
    assert result.knowledge_deleted == 2
    assert remaining == preserved_ids
    assert not remaining.intersection(deleted_ids)
    assert session.get(FakeGuardAuditEvent, raw_audit.id) is not None


def test_expired_knowledge_deletes_from_expires_at_despite_fresh_update():
    session = _session()
    row = _knowledge(
        session,
        "ws-a",
        "audit_event",
        NOW - timedelta(days=30),
        updated_at=NOW,
    )
    session.commit()
    row_id = row.id

    result = cleanup_expired_projections(
        session,
        workspace_id="ws-a",
        now=NOW,
        model_overrides={"knowledge": FakeKnowledge},
    )
    session.commit()

    assert result.knowledge_deleted == 1
    assert session.get(FakeKnowledge, row_id) is None


def test_intent_model_requires_source_kind():
    session = _session()

    with pytest.raises(
        TypeError, match="intent model is missing required retention fields"
    ):
        cleanup_expired_projections(
            session,
            workspace_id="ws-a",
            now=NOW,
            model_overrides={"intent": FakeIntentWithoutSourceKind},
        )


def test_intents_only_terminalize_retryable_expired_states():
    session = _session()
    expired = [
        _intent(session, "ws-a", status, NOW)
        for status in ("pending", "retry", "dead_letter")
    ]
    completed = _intent(session, "ws-a", "completed", NOW)
    processing = _intent(session, "ws-a", "processing", NOW)
    future = _intent(session, "ws-a", "retry", NOW + timedelta(seconds=1))
    no_expiry = _intent(session, "ws-a", "pending", None)
    other = _intent(session, "ws-b", "pending", NOW)
    rule = _intent(session, "ws-a", "pending", NOW, source_kind="rule")
    agent = _intent(session, "ws-a", "retry", NOW, source_kind="discovered_agent")
    session.commit()
    dead_letter_id = expired[2].id
    completed_id = completed.id

    result = cleanup_expired_projections(
        session, workspace_id="ws-a", now=NOW, model_overrides=MODELS
    )
    session.commit()
    session.expire_all()

    assert result.intents_expired == 2
    assert result.intents_deleted == 2
    assert [row.status for row in expired[:2]] == ["expired", "expired"]
    assert session.get(FakeIntent, dead_letter_id) is None
    assert session.get(FakeIntent, completed_id) is None
    assert processing.status == "processing"
    assert future.status == "retry"
    assert no_expiry.status == "pending"
    assert other.status == "pending"
    assert rule.status == "pending"
    assert agent.status == "retry"


def test_expired_summaries_delete_only_without_processing_intent():
    session = _session()
    deletable = _summary(session, "ws-a", NOW)
    in_flight = _summary(session, "ws-a", NOW)
    other_workspace = _summary(session, "ws-b", NOW)
    processing = _intent(
        session,
        "ws-a",
        "processing",
        NOW,
        source_kind="audit_summary",
    )
    processing.source_id = str(in_flight.id)
    session.commit()
    deletable_id = deletable.id
    in_flight_id = in_flight.id
    other_id = other_workspace.id

    result = cleanup_expired_projections(
        session, workspace_id="ws-a", now=NOW, model_overrides=MODELS
    )
    session.commit()

    assert result.summaries_deleted == 1
    assert session.get(FakeSummary, deletable_id) is None
    assert session.get(FakeSummary, in_flight_id) is not None
    assert session.get(FakeSummary, other_id) is not None
    assert processing.status == "processing"


def test_cleanup_is_bounded_deterministic_and_resumable():
    session = _session()
    rows = [
        _knowledge(session, "ws-a", "audit_event", NOW - timedelta(days=days))
        for days in (1, 3, 2)
    ]
    session.commit()
    oldest_id = rows[1].id

    first = cleanup_expired_projections(
        session,
        workspace_id="ws-a",
        batch_size=1,
        now=NOW,
        model_overrides={"knowledge": FakeKnowledge},
    )
    session.commit()
    remaining_after_first = set(session.scalars(select(FakeKnowledge.id)))
    second = cleanup_expired_projections(
        session,
        workspace_id="ws-a",
        batch_size=1,
        now=NOW,
        model_overrides={"knowledge": FakeKnowledge},
    )
    session.commit()

    assert oldest_id not in remaining_after_first
    assert first.knowledge_deleted == second.knowledge_deleted == 1
    assert first.more_work is True
    assert len(list(session.scalars(select(FakeKnowledge.id)))) == 1


def test_dry_run_aggregates_workspace_counts_without_mutation_or_commit():
    session = _session()
    _knowledge(session, "ws-a", "audit_event", NOW)
    _knowledge(session, "ws-b", "audit_event", NOW)
    _intent(session, "ws-a", "retry", NOW)
    session.commit()
    commits = 0
    original_commit = session.commit

    def tracking_commit():
        nonlocal commits
        commits += 1
        original_commit()

    session.commit = tracking_commit
    result = cleanup_expired_projections(
        session,
        workspace_id="ws-a",
        dry_run=True,
        now=NOW,
        model_overrides=MODELS,
    )

    assert result.to_dict() == {
        "dry_run": True,
        "backfill_candidates": 0,
        "knowledge_backfilled": 0,
        "knowledge_orphans_deleted": 0,
        "knowledge_candidates": 1,
        "knowledge_deleted": 0,
        "summary_candidates": 0,
        "summaries_deleted": 0,
        "intent_candidates": 1,
        "intents_expired": 0,
        "intent_delete_candidates": 0,
        "intents_deleted": 0,
        "batches_committed": 0,
        "more_work": False,
    }
    assert commits == 0
    assert session.scalar(
        select(FakeKnowledge).where(FakeKnowledge.workspace_id == "ws-a")
    )


def test_cleanup_never_commits_or_rolls_back_caller_work():
    engine, factory = _session_factory()
    session = factory()
    expired = _knowledge(session, "ws-a", "audit_event", NOW)
    session.commit()
    expired_id = expired.id
    unrelated = _knowledge(session, "ws-a", "rule", None)
    commits = 0
    rollbacks = 0
    original_commit = session.commit
    original_rollback = session.rollback

    def tracking_commit():
        nonlocal commits
        commits += 1
        original_commit()

    def tracking_rollback():
        nonlocal rollbacks
        rollbacks += 1
        original_rollback()

    session.commit = tracking_commit
    session.rollback = tracking_rollback

    result = cleanup_expired_projections(
        session, workspace_id="ws-a", now=NOW, model_overrides={"knowledge": FakeKnowledge}
    )

    assert result.knowledge_deleted == 1
    assert result.batches_committed == 0
    assert commits == rollbacks == 0
    assert unrelated in session
    assert session.in_transaction()

    original_rollback()
    with factory() as verifier:
        assert verifier.get(FakeKnowledge, expired_id) is not None
        assert (
            verifier.scalar(
                select(FakeKnowledge.id).where(FakeKnowledge.source_kind == "rule")
            )
            is None
        )
    engine.dispose()


def test_cleanup_error_does_not_rollback_pending_caller_work(monkeypatch):
    session = _session()
    unrelated = _knowledge(session, "ws-a", "rule", None)
    rollbacks = 0
    original_rollback = session.rollback

    def tracking_rollback():
        nonlocal rollbacks
        rollbacks += 1
        original_rollback()

    def fail_batch(*args, **kwargs):
        raise RuntimeError("forced cleanup failure")

    session.rollback = tracking_rollback
    monkeypatch.setattr(retention, "_delete_batch", fail_batch)

    with pytest.raises(RuntimeError, match="forced cleanup failure"):
        cleanup_expired_projections(
            session, workspace_id="ws-a", now=NOW, model_overrides={"knowledge": FakeKnowledge}
        )

    assert rollbacks == 0
    assert unrelated in session.new
    assert session.in_transaction()
    original_rollback()


def test_lazy_model_override_does_not_require_current_schema():
    session = _session()
    _knowledge(session, "ws-a", "audit_event", NOW)
    session.commit()

    result = cleanup_expired_projections(
        session, workspace_id="ws-a", now=NOW, model_overrides={"knowledge_model": FakeKnowledge}
    )

    assert result.knowledge_deleted == 1
    assert result.intents_expired == 0
