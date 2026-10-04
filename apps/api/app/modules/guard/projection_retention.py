# Bounded retention for Guard search projections and durable projection sources.
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.core.workspace_context import set_workspace_rls
from app.models.workspace import Workspace
from app.modules.guard.projection_contract import ProjectionIntentStatus

log = structlog.get_logger(__name__)
DEFAULT_RETENTION_BATCH_SIZE = 500
_EXPIRING_SOURCE_KINDS = ('audit_event', 'audit_summary')
_EXPIRABLE_INTENT_STATUSES = (
    ProjectionIntentStatus.PENDING.value,
    ProjectionIntentStatus.RETRY.value,
)
_DELETABLE_INTENT_STATUSES = (
    ProjectionIntentStatus.COMPLETED.value,
    ProjectionIntentStatus.SUPERSEDED.value,
    ProjectionIntentStatus.EXPIRED.value,
    ProjectionIntentStatus.MISSING.value,
    ProjectionIntentStatus.DEAD_LETTER.value,
)
_SQL_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


@dataclass(frozen=True)
class ProjectionRetentionResult:
    dry_run: bool
    backfill_candidates: int = 0
    knowledge_backfilled: int = 0
    knowledge_orphans_deleted: int = 0
    knowledge_candidates: int = 0
    knowledge_deleted: int = 0
    summary_candidates: int = 0
    summaries_deleted: int = 0
    intent_candidates: int = 0
    intents_expired: int = 0
    intent_delete_candidates: int = 0
    intents_deleted: int = 0
    batches_committed: int = 0
    more_work: bool = False

    def to_dict(self) -> dict[str, bool | int]:
        return asdict(self)


def filter_active_projections(
    query: Any, *, model: Any, workspace_id: Any, now: datetime | None = None
) -> Any:
    if workspace_id is None or (
        isinstance(workspace_id, str) and not workspace_id.strip()
    ):
        raise ValueError('workspace_id is required')
    cutoff = now if now is not None else func.now()
    predicates = (
        model.workspace_id == workspace_id,
        or_(model.expires_at.is_(None), model.expires_at > cutoff),
    )
    if hasattr(query, 'where'):
        return query.where(*predicates)
    return query.filter(*predicates)


apply_projection_search_filter = filter_active_projections


def active_projection_sql_predicate(
    alias: str,
    *,
    workspace_param: str = 'workspace_id',
    now_param: str = 'projection_now',
) -> str:
    identifiers = {
        'alias': alias,
        'workspace_param': workspace_param,
        'now_param': now_param,
    }
    for label, identifier in identifiers.items():
        if not isinstance(identifier, str) or not _SQL_IDENTIFIER.fullmatch(identifier):
            raise ValueError(f'{label} must be a safe SQL identifier')
    return (
        f'{alias}.workspace_id = CAST(:{workspace_param} AS uuid) '
        f'AND ({alias}.expires_at IS NULL OR {alias}.expires_at > :{now_param})'
    )


def _override(model_overrides: Mapping[str, Any] | None, *names: str) -> Any | None:
    if not model_overrides:
        return None
    for name in names:
        if name in model_overrides:
            return model_overrides[name]
    return None


def _resolve_models(
    model_overrides: Mapping[str, Any] | None,
) -> tuple[Any | None, Any | None, Any | None]:
    knowledge_model = _override(
        model_overrides, 'knowledge', 'knowledge_model', 'GuardKnowledgeIndex'
    )
    intent_model = _override(
        model_overrides, 'intent', 'intent_model', 'GuardProjectionIntent', 'ProjectionIntent'
    )
    summary_model = _override(
        model_overrides, 'summary', 'summary_model', 'GuardProjectionSummary'
    )
    if model_overrides is not None:
        return knowledge_model, intent_model, summary_model

    from app.modules.guard import models as guard_models

    if knowledge_model is None:
        candidate = getattr(guard_models, 'GuardKnowledgeIndex', None)
        if candidate is not None and hasattr(candidate, 'expires_at'):
            knowledge_model = candidate
    if intent_model is None:
        candidate = getattr(guard_models, 'GuardProjectionIntent', None)
        if candidate is not None and hasattr(candidate, 'expires_at'):
            intent_model = candidate
    if summary_model is None:
        candidate = getattr(guard_models, 'GuardProjectionSummary', None)
        if candidate is not None and hasattr(candidate, 'expires_at'):
            summary_model = candidate
    return knowledge_model, intent_model, summary_model


def _validate_model(model: Any, required: tuple[str, ...], label: str) -> None:
    if any(not hasattr(model, name) for name in required):
        raise TypeError(f'{label} model is missing required retention fields')


def _validate_retention_models(
    knowledge_model: Any | None,
    intent_model: Any | None,
    summary_model: Any | None,
) -> None:
    if knowledge_model is not None:
        _validate_model(knowledge_model, ('id', 'workspace_id', 'source_kind', 'expires_at'), 'knowledge')
    if intent_model is not None:
        _validate_model(intent_model, ('id', 'workspace_id', 'source_kind', 'source_id', 'status', 'expires_at'), 'intent')
    if summary_model is not None:
        _validate_model(summary_model, ('id', 'workspace_id', 'expires_at'), 'summary')


def _resolve_backfill_models(
    model_overrides: Mapping[str, Any] | None,
) -> tuple[Any | None, Any | None, Any | None]:
    knowledge_model = _override(
        model_overrides, 'knowledge', 'knowledge_model', 'GuardKnowledgeIndex'
    )
    audit_event_model = _override(
        model_overrides, 'audit_event', 'audit_event_model', 'GuardAuditEvent'
    )
    summary_model = _override(
        model_overrides, 'summary', 'summary_model', 'GuardProjectionSummary'
    )
    if model_overrides is not None:
        return knowledge_model, audit_event_model, summary_model
    from app.modules.guard import models as guard_models

    return (
        getattr(guard_models, 'GuardKnowledgeIndex', None),
        getattr(guard_models, 'GuardAuditEvent', None),
        getattr(guard_models, 'GuardProjectionSummary', None),
    )


def _backfill_predicates(
    model: Any, workspace_id: Any, source_kinds: tuple[str, ...]
) -> tuple[Any, ...]:
    return (
        model.workspace_id == workspace_id,
        model.source_kind.in_(source_kinds),
        or_(model.source_timestamp.is_(None), model.expires_at.is_(None)),
    )


def backfill_projection_expiry(
    db: Session,
    *,
    workspace_id: Any,
    retention_days: int,
    batch_size: int = DEFAULT_RETENTION_BATCH_SIZE,
    dry_run: bool = False,
    model_overrides: Mapping[str, Any] | None = None,
) -> ProjectionRetentionResult:
    """Backfill legacy derived projection expiry in one restart-safe batch."""
    _validate_batch_size(batch_size)
    if retention_days <= 0:
        raise ValueError('retention_days must be positive')
    knowledge_model, audit_event_model, summary_model = _resolve_backfill_models(
        model_overrides
    )
    if knowledge_model is None:
        return ProjectionRetentionResult(dry_run=dry_run)
    _validate_model(
        knowledge_model,
        ('id', 'workspace_id', 'source_kind', 'source_id', 'source_timestamp', 'expires_at'),
        'knowledge',
    )
    source_kinds = tuple(
        kind
        for kind, source_model in (
            ('audit_event', audit_event_model),
            ('audit_summary', summary_model),
        )
        if source_model is not None
    )
    if not source_kinds:
        return ProjectionRetentionResult(dry_run=dry_run)
    set_workspace_rls(db, workspace_id)
    predicates = _backfill_predicates(knowledge_model, workspace_id, source_kinds)
    if dry_run:
        return ProjectionRetentionResult(
            dry_run=True,
            backfill_candidates=_count_candidates(db, knowledge_model, predicates),
        )
    rows = list(
        db.execute(
            select(knowledge_model)
            .where(*predicates)
            .order_by(knowledge_model.source_kind.asc(), knowledge_model.id.asc())
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        ).scalars()
    )
    backfilled = orphans_deleted = 0
    for row in rows:
        source = None
        if row.source_kind == 'audit_event' and audit_event_model is not None:
            source = db.execute(
                select(audit_event_model).where(
                    audit_event_model.workspace_id == workspace_id,
                    func.cast(audit_event_model.id, knowledge_model.source_id.type)
                    == row.source_id,
                )
            ).scalar_one_or_none()
            source_timestamp = source.ts if source is not None else None
            source_expiry = (
                source_timestamp + timedelta(days=retention_days)
                if source_timestamp is not None
                else None
            )
        elif row.source_kind == 'audit_summary' and summary_model is not None:
            source = db.execute(
                select(summary_model).where(
                    summary_model.workspace_id == workspace_id,
                    func.cast(summary_model.id, knowledge_model.source_id.type)
                    == row.source_id,
                )
            ).scalar_one_or_none()
            source_timestamp = (
                getattr(source, 'source_timestamp', None)
                or getattr(source, 'window_end', None)
                if source is not None
                else None
            )
            source_expiry = (
                getattr(source, 'expires_at', None)
                or (source_timestamp + timedelta(days=retention_days) if source_timestamp else None)
                if source is not None
                else None
            )
        else:
            continue
        if source is None or source_timestamp is None or source_expiry is None:
            db.delete(row)
            orphans_deleted += 1
            continue
        row.source_timestamp = source_timestamp
        row.expires_at = source_expiry
        backfilled += 1
    return ProjectionRetentionResult(
        dry_run=False,
        backfill_candidates=len(rows),
        knowledge_backfilled=backfilled,
        knowledge_orphans_deleted=orphans_deleted,
        more_work=len(rows) == batch_size,
    )


def _validate_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError('batch_size must be a positive integer')
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')


def _candidate_ids(
    db: Session, model: Any, predicates: tuple[Any, ...], batch_size: int
) -> list[Any]:
    statement = (
        select(model.id)
        .where(*predicates)
        .order_by(model.expires_at.asc(), model.id.asc())
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )
    return list(db.execute(statement).scalars())


def _count_candidates(db: Session, model: Any, predicates: tuple[Any, ...]) -> int:
    return int(db.execute(select(func.count()).select_from(model).where(*predicates)).scalar_one())


def _knowledge_predicates(model: Any, workspace_id: Any, cutoff: Any) -> tuple[Any, ...]:
    return (
        model.workspace_id == workspace_id,
        model.source_kind.in_(_EXPIRING_SOURCE_KINDS),
        model.expires_at.is_not(None),
        model.expires_at <= cutoff,
    )


def _intent_expire_predicates(model: Any, workspace_id: Any, cutoff: Any) -> tuple[Any, ...]:
    return (
        model.workspace_id == workspace_id,
        model.source_kind.in_(_EXPIRING_SOURCE_KINDS),
        model.status.in_(_EXPIRABLE_INTENT_STATUSES),
        model.expires_at.is_not(None),
        model.expires_at <= cutoff,
    )


def _intent_delete_predicates(model: Any, workspace_id: Any, cutoff: Any) -> tuple[Any, ...]:
    return (
        model.workspace_id == workspace_id,
        model.source_kind.in_(_EXPIRING_SOURCE_KINDS),
        model.status.in_(_DELETABLE_INTENT_STATUSES),
        model.expires_at.is_not(None),
        model.expires_at <= cutoff,
    )


def _summary_predicates(
    model: Any, intent_model: Any | None, workspace_id: Any, cutoff: Any
) -> tuple[Any, ...]:
    predicates = [
        model.workspace_id == workspace_id,
        model.expires_at <= cutoff,
    ]
    if intent_model is not None:
        active_intent = select(intent_model.id).where(
            intent_model.workspace_id == workspace_id,
            intent_model.source_kind == 'audit_summary',
            intent_model.source_id == func.cast(model.id, intent_model.source_id.type),
            intent_model.status == ProjectionIntentStatus.PROCESSING.value,
        )
        predicates.append(~active_intent.exists())
    return tuple(predicates)


def _delete_batch(db: Session, *, model: Any, predicates: tuple[Any, ...], batch_size: int) -> tuple[int, int]:
    candidate_ids = _candidate_ids(db, model, predicates, batch_size)
    if not candidate_ids:
        return 0, 0
    result = db.execute(
        delete(model)
        .where(model.id.in_(candidate_ids), *predicates)
        .execution_options(synchronize_session=False)
    )
    return len(candidate_ids), result.rowcount or 0


def _expire_intent_batch(
    db: Session, *, model: Any, workspace_id: Any, cutoff: Any, batch_size: int
) -> tuple[int, int]:
    predicates = _intent_expire_predicates(model, workspace_id, cutoff)
    candidate_ids = _candidate_ids(db, model, predicates, batch_size)
    if not candidate_ids:
        return 0, 0
    result = db.execute(
        update(model)
        .where(model.id.in_(candidate_ids), *predicates)
        .values(
            status=ProjectionIntentStatus.EXPIRED.value,
            completed_at=cutoff,
            lease_expires_at=None,
            dispatched_at=None,
        )
        .execution_options(synchronize_session=False)
    )
    return len(candidate_ids), result.rowcount or 0


def cleanup_expired_projections(
    db: Session,
    *,
    workspace_id: Any,
    batch_size: int = DEFAULT_RETENTION_BATCH_SIZE,
    dry_run: bool = False,
    now: datetime | None = None,
    model_overrides: Mapping[str, Any] | None = None,
) -> ProjectionRetentionResult:
    _validate_batch_size(batch_size)
    if workspace_id is None or (isinstance(workspace_id, str) and not workspace_id.strip()):
        raise ValueError('workspace_id is required for retention')
    knowledge_model, intent_model, summary_model = _resolve_models(model_overrides)
    _validate_retention_models(knowledge_model, intent_model, summary_model)
    set_workspace_rls(db, workspace_id)
    cutoff = now if now is not None else func.now()

    knowledge_predicates = _knowledge_predicates(knowledge_model, workspace_id, cutoff) if knowledge_model is not None else ()
    expire_predicates = _intent_expire_predicates(intent_model, workspace_id, cutoff) if intent_model is not None else ()
    delete_predicates = _intent_delete_predicates(intent_model, workspace_id, cutoff) if intent_model is not None else ()
    summary_predicates = _summary_predicates(summary_model, intent_model, workspace_id, cutoff) if summary_model is not None else ()

    if dry_run:
        return ProjectionRetentionResult(
            dry_run=True,
            knowledge_candidates=_count_candidates(db, knowledge_model, knowledge_predicates) if knowledge_model is not None else 0,
            summary_candidates=_count_candidates(db, summary_model, summary_predicates) if summary_model is not None else 0,
            intent_candidates=_count_candidates(db, intent_model, expire_predicates) if intent_model is not None else 0,
            intent_delete_candidates=_count_candidates(db, intent_model, delete_predicates) if intent_model is not None else 0,
        )

    knowledge_candidates = knowledge_deleted = 0
    intent_candidates = intents_expired = 0
    intent_delete_candidates = intents_deleted = 0
    summary_candidates = summaries_deleted = 0
    if knowledge_model is not None:
        knowledge_candidates, knowledge_deleted = _delete_batch(
            db, model=knowledge_model, predicates=knowledge_predicates, batch_size=batch_size
        )
    if intent_model is not None:
        delete_ids = _candidate_ids(db, intent_model, delete_predicates, batch_size)
        intent_candidates, intents_expired = _expire_intent_batch(
            db, model=intent_model, workspace_id=workspace_id, cutoff=cutoff, batch_size=batch_size
        )
        intent_delete_candidates = len(delete_ids)
        if delete_ids:
            deleted = db.execute(
                delete(intent_model)
                .where(intent_model.id.in_(delete_ids), *delete_predicates)
                .execution_options(synchronize_session=False)
            )
            intents_deleted = deleted.rowcount or 0
    if summary_model is not None:
        summary_predicates = _summary_predicates(summary_model, intent_model, workspace_id, cutoff)
        summary_candidates, summaries_deleted = _delete_batch(
            db, model=summary_model, predicates=summary_predicates, batch_size=batch_size
        )
    counts = (knowledge_candidates, intent_candidates, intent_delete_candidates, summary_candidates)
    return ProjectionRetentionResult(
        dry_run=False,
        knowledge_candidates=knowledge_candidates,
        knowledge_deleted=knowledge_deleted,
        summary_candidates=summary_candidates,
        summaries_deleted=summaries_deleted,
        intent_candidates=intent_candidates,
        intents_expired=intents_expired,
        intent_delete_candidates=intent_delete_candidates,
        intents_deleted=intents_deleted,
        more_work=any(count == batch_size for count in counts),
    )


def _workspace_ids(session_factory: Callable[[], Session], workspace_id: Any | None) -> list[Any]:
    if workspace_id is not None:
        return [workspace_id]
    session = session_factory()
    try:
        return list(session.execute(select(Workspace.id).order_by(Workspace.id)).scalars())
    finally:
        if session.in_transaction():
            session.rollback()
        session.close()


def _merge_results(results: list[ProjectionRetentionResult], *, dry_run: bool, commits: int) -> ProjectionRetentionResult:
    fields = (
        'backfill_candidates', 'knowledge_backfilled',
        'knowledge_orphans_deleted', 'knowledge_candidates',
        'knowledge_deleted', 'summary_candidates',
        'summaries_deleted', 'intent_candidates', 'intents_expired',
        'intent_delete_candidates', 'intents_deleted',
    )
    totals = {field: sum(getattr(result, field) for result in results) for field in fields}
    return ProjectionRetentionResult(
        dry_run=dry_run,
        batches_committed=commits,
        more_work=any(result.more_work for result in results),
        **totals,
    )


def run_projection_retention_once(
    db: Session | None = None,
    *,
    session_factory: Callable[[], Session] | None = None,
    workspace_id: Any | None = None,
    batch_size: int | None = None,
    dry_run: bool = False,
    now: datetime | None = None,
    model_overrides: Mapping[str, Any] | None = None,
    settings_override: Any | None = None,
    on_result: Callable[[Mapping[str, bool | int]], None] | None = None,
) -> ProjectionRetentionResult:
    if db is not None:
        raise ValueError('run_projection_retention_once does not accept a caller-owned db session; pass session_factory so each batch can use an independent transaction')
    settings_obj = settings_override
    if settings_obj is None:
        from app.core.config import settings as settings_obj
    if batch_size is None:
        batch_size = int(getattr(settings_obj, 'guard_projection_prune_batch_size', DEFAULT_RETENTION_BATCH_SIZE))
    _validate_batch_size(batch_size)
    if session_factory is None:
        from app.core.database import SessionLocal
        session_factory = SessionLocal

    models = _resolve_models(model_overrides)
    _validate_retention_models(*models)
    workspace_ids = _workspace_ids(session_factory, workspace_id)
    results: list[ProjectionRetentionResult] = []
    commits = 0
    for current_workspace_id in workspace_ids:
        if dry_run:
            session = session_factory()
            try:
                backfill_result = backfill_projection_expiry(
                    session,
                    workspace_id=current_workspace_id,
                    retention_days=int(getattr(settings_obj, 'guard_projection_retention_days', 30)),
                    batch_size=batch_size,
                    dry_run=True,
                    model_overrides=model_overrides,
                )
                cleanup_result = cleanup_expired_projections(
                    session,
                    workspace_id=current_workspace_id,
                    batch_size=batch_size,
                    dry_run=True,
                    now=now,
                    model_overrides=model_overrides,
                )
                results.append(
                    _merge_results([backfill_result, cleanup_result], dry_run=True, commits=0)
                )
            finally:
                if session.in_transaction():
                    session.rollback()
                session.close()
            continue

        workspace_results: list[ProjectionRetentionResult] = []
        backfill_session = session_factory()
        try:
            backfill_result = backfill_projection_expiry(
                backfill_session,
                workspace_id=current_workspace_id,
                retention_days=int(getattr(settings_obj, 'guard_projection_retention_days', 30)),
                batch_size=batch_size,
                dry_run=False,
                model_overrides=model_overrides,
            )
            if backfill_result.knowledge_backfilled + backfill_result.knowledge_orphans_deleted:
                backfill_session.commit()
                commits += 1
            elif backfill_session.in_transaction():
                backfill_session.rollback()
            workspace_results.append(backfill_result)
        except Exception:
            if backfill_session.in_transaction():
                backfill_session.rollback()
            log.error('guard.projection_retention.backfill_failed', dry_run=False, batch_size=batch_size)
            raise
        finally:
            backfill_session.close()

        stage_overrides = (
            {'knowledge': models[0]},
            {'intent': models[1]},
            {'summary': models[2], 'intent': models[1]},
        )
        for overrides in stage_overrides:
            if all(value is None for value in overrides.values()):
                continue
            session = session_factory()
            try:
                stage_result = cleanup_expired_projections(
                    session,
                    workspace_id=current_workspace_id,
                    batch_size=batch_size,
                    dry_run=False,
                    now=now,
                    model_overrides=overrides,
                )
                changed = (
                    stage_result.knowledge_deleted
                    + stage_result.intents_expired
                    + stage_result.intents_deleted
                    + stage_result.summaries_deleted
                )
                if changed:
                    session.commit()
                    commits += 1
                elif session.in_transaction():
                    session.rollback()
                workspace_results.append(stage_result)
            except Exception:
                if session.in_transaction():
                    session.rollback()
                log.error('guard.projection_retention.failed', dry_run=False, batch_size=batch_size)
                raise
            finally:
                session.close()
        results.append(_merge_results(workspace_results, dry_run=False, commits=0))

    result = _merge_results(results, dry_run=dry_run, commits=commits)
    aggregate = result.to_dict()
    log.info('guard.projection_retention.completed', **aggregate)
    if on_result is not None:
        on_result(aggregate)
    return result
