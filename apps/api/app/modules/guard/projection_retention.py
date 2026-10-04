# Bounded retention for Guard search projections and projection intents.
# Models resolve lazily because the projection schema ships separately.
from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from app.modules.guard.projection_contract import ProjectionIntentStatus

log = structlog.get_logger(__name__)
DEFAULT_RETENTION_BATCH_SIZE = 500
_EXPIRING_SOURCE_KINDS = ("audit_event", "audit_summary")
_EXPIRABLE_INTENT_STATUSES = (
    ProjectionIntentStatus.PENDING.value,
    ProjectionIntentStatus.RETRY.value,
    ProjectionIntentStatus.DEAD_LETTER.value,
)
_SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class ProjectionRetentionResult:
    """Aggregate-only retention outcome safe for logs, callbacks, and workers.

    ``batches_committed`` is zero for ``cleanup_expired_projections`` because
    that helper never controls its caller transaction. The worker entrypoint
    reports the number of dedicated batch transactions it committed.
    """

    dry_run: bool
    knowledge_candidates: int = 0
    knowledge_deleted: int = 0
    intent_candidates: int = 0
    intents_expired: int = 0
    batches_committed: int = 0
    more_work: bool = False

    def to_dict(self) -> dict[str, bool | int]:
        return asdict(self)


def filter_active_projections(
    query: Any, *, model: Any, workspace_id: Any, now: datetime | None = None
) -> Any:
    # Apply mandatory workspace and non-expired search predicates together.
    if workspace_id is None or (
        isinstance(workspace_id, str) and not workspace_id.strip()
    ):
        raise ValueError("workspace_id is required")

    cutoff = now if now is not None else func.now()
    predicates = (
        model.workspace_id == workspace_id,
        or_(model.expires_at.is_(None), model.expires_at > cutoff),
    )
    if hasattr(query, "where"):
        return query.where(*predicates)
    return query.filter(*predicates)


apply_projection_search_filter = filter_active_projections


def active_projection_sql_predicate(
    alias: str,
    *,
    workspace_param: str = "workspace_id",
    now_param: str = "projection_now",
) -> str:
    # SQL identifiers cannot be bound, so reject unsafe interpolation inputs.
    identifiers = {
        "alias": alias,
        "workspace_param": workspace_param,
        "now_param": now_param,
    }
    for label, identifier in identifiers.items():
        if not isinstance(identifier, str) or not _SQL_IDENTIFIER.fullmatch(identifier):
            raise ValueError(f"{label} must be a safe SQL identifier")
    return (
        f"{alias}.workspace_id = CAST(:{workspace_param} AS uuid) "
        f"AND ({alias}.expires_at IS NULL OR {alias}.expires_at > :{now_param})"
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
) -> tuple[Any | None, Any | None]:
    # Avoid importing model definitions until the retention job actually runs.
    knowledge_model = _override(
        model_overrides, "knowledge", "knowledge_model", "GuardKnowledgeIndex"
    )
    intent_model = _override(
        model_overrides,
        "intent",
        "intent_model",
        "GuardProjectionIntent",
        "ProjectionIntent",
    )
    if knowledge_model is not None and intent_model is not None:
        return knowledge_model, intent_model

    from app.modules.guard import models as guard_models

    if knowledge_model is None:
        candidate = getattr(guard_models, "GuardKnowledgeIndex", None)
        if candidate is not None and hasattr(candidate, "expires_at"):
            knowledge_model = candidate
    if intent_model is None:
        for name in ("GuardProjectionIntent", "ProjectionIntent"):
            candidate = getattr(guard_models, name, None)
            if candidate is not None and hasattr(candidate, "expires_at"):
                intent_model = candidate
                break
    return knowledge_model, intent_model


def _validate_model(model: Any, required: tuple[str, ...], label: str) -> None:
    if any(not hasattr(model, name) for name in required):
        raise TypeError(f"{label} model is missing required retention fields")


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
    statement = select(func.count()).select_from(model).where(*predicates)
    return int(db.execute(statement).scalar_one())


def _knowledge_predicates(
    model: Any, workspace_id: Any | None, cutoff: Any
) -> tuple[Any, ...]:
    predicates = [
        model.source_kind.in_(_EXPIRING_SOURCE_KINDS),
        model.expires_at.is_not(None),
        model.expires_at <= cutoff,
    ]
    if workspace_id is not None:
        predicates.append(model.workspace_id == workspace_id)
    return tuple(predicates)


def _intent_predicates(
    model: Any, workspace_id: Any | None, cutoff: Any
) -> tuple[Any, ...]:
    predicates = [
        model.source_kind.in_(_EXPIRING_SOURCE_KINDS),
        model.status.in_(_EXPIRABLE_INTENT_STATUSES),
        model.expires_at.is_not(None),
        model.expires_at <= cutoff,
    ]
    if workspace_id is not None:
        predicates.append(model.workspace_id == workspace_id)
    return tuple(predicates)


def _validate_batch_size(batch_size: int) -> None:
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size must be a positive integer")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")


def _validate_retention_models(
    knowledge_model: Any | None, intent_model: Any | None
) -> None:
    if knowledge_model is not None:
        _validate_model(
            knowledge_model,
            ("id", "workspace_id", "source_kind", "expires_at"),
            "knowledge",
        )
    if intent_model is not None:
        _validate_model(
            intent_model,
            ("id", "workspace_id", "source_kind", "status", "expires_at"),
            "intent",
        )


def _cleanup_knowledge_batch(
    db: Session,
    *,
    model: Any,
    workspace_id: Any | None,
    cutoff: Any,
    batch_size: int,
) -> tuple[int, int]:
    predicates = _knowledge_predicates(model, workspace_id, cutoff)
    candidate_ids = _candidate_ids(db, model, predicates, batch_size)
    if not candidate_ids:
        return 0, 0
    result = db.execute(
        delete(model)
        .where(
            model.id.in_(candidate_ids),
            *_knowledge_predicates(model, workspace_id, cutoff),
        )
        .execution_options(synchronize_session=False)
    )
    return len(candidate_ids), result.rowcount or 0


def _cleanup_intent_batch(
    db: Session,
    *,
    model: Any,
    workspace_id: Any | None,
    cutoff: Any,
    batch_size: int,
) -> tuple[int, int]:
    predicates = _intent_predicates(model, workspace_id, cutoff)
    candidate_ids = _candidate_ids(db, model, predicates, batch_size)
    if not candidate_ids:
        return 0, 0
    result = db.execute(
        update(model)
        .where(
            model.id.in_(candidate_ids),
            *_intent_predicates(model, workspace_id, cutoff),
        )
        .values(status=ProjectionIntentStatus.EXPIRED.value)
        .execution_options(synchronize_session=False)
    )
    return len(candidate_ids), result.rowcount or 0


def cleanup_expired_projections(
    db: Session,
    *,
    workspace_id: Any | None = None,
    batch_size: int = DEFAULT_RETENTION_BATCH_SIZE,
    dry_run: bool = False,
    now: datetime | None = None,
    model_overrides: Mapping[str, Any] | None = None,
) -> ProjectionRetentionResult:
    """Mutate one bounded pass inside the caller-owned transaction.

    This helper never commits or rolls back. Callers decide whether all
    knowledge and intent mutations should be committed or rolled back together.
    Use ``run_projection_retention_once`` for independently committed batches.
    """
    _validate_batch_size(batch_size)
    knowledge_model, intent_model = _resolve_models(model_overrides)
    _validate_retention_models(knowledge_model, intent_model)
    cutoff = now if now is not None else func.now()

    if dry_run:
        knowledge_count = (
            _count_candidates(
                db,
                knowledge_model,
                _knowledge_predicates(knowledge_model, workspace_id, cutoff),
            )
            if knowledge_model is not None
            else 0
        )
        intent_count = (
            _count_candidates(
                db,
                intent_model,
                _intent_predicates(intent_model, workspace_id, cutoff),
            )
            if intent_model is not None
            else 0
        )
        return ProjectionRetentionResult(
            dry_run=True,
            knowledge_candidates=knowledge_count,
            intent_candidates=intent_count,
        )

    knowledge_candidates = 0
    knowledge_deleted = 0
    intent_candidates = 0
    intents_expired = 0
    if knowledge_model is not None:
        knowledge_candidates, knowledge_deleted = _cleanup_knowledge_batch(
            db,
            model=knowledge_model,
            workspace_id=workspace_id,
            cutoff=cutoff,
            batch_size=batch_size,
        )
    if intent_model is not None:
        intent_candidates, intents_expired = _cleanup_intent_batch(
            db,
            model=intent_model,
            workspace_id=workspace_id,
            cutoff=cutoff,
            batch_size=batch_size,
        )

    return ProjectionRetentionResult(
        dry_run=False,
        knowledge_candidates=knowledge_candidates,
        knowledge_deleted=knowledge_deleted,
        intent_candidates=intent_candidates,
        intents_expired=intents_expired,
        more_work=(
            knowledge_candidates == batch_size or intent_candidates == batch_size
        ),
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
    """Run independently committed retention batches in dedicated sessions."""
    if db is not None:
        raise ValueError(
            "run_projection_retention_once does not accept a caller-owned db "
            "session; pass session_factory so each batch can use an independent "
            "transaction"
        )

    if batch_size is None:
        settings_obj = settings_override
        if settings_obj is None:
            from app.core.config import settings as settings_obj
        batch_size = int(
            getattr(
                settings_obj,
                "guard_projection_prune_batch_size",
                DEFAULT_RETENTION_BATCH_SIZE,
            )
        )
    _validate_batch_size(batch_size)

    if session_factory is None:
        from app.core.database import SessionLocal

        session_factory = SessionLocal

    knowledge_model, intent_model = _resolve_models(model_overrides)
    _validate_retention_models(knowledge_model, intent_model)
    cutoff = now if now is not None else func.now()

    if dry_run:
        session = session_factory()
        try:
            result = cleanup_expired_projections(
                session,
                workspace_id=workspace_id,
                batch_size=batch_size,
                dry_run=True,
                now=now,
                model_overrides=model_overrides,
            )
        finally:
            if session.in_transaction():
                session.rollback()
            session.close()
    else:
        knowledge_candidates = 0
        knowledge_deleted = 0
        intent_candidates = 0
        intents_expired = 0
        commits = 0
        batches = (
            ("knowledge", knowledge_model, _cleanup_knowledge_batch),
            ("intent", intent_model, _cleanup_intent_batch),
        )
        for label, model, cleanup_batch in batches:
            if model is None:
                continue
            session = session_factory()
            try:
                candidates, changed = cleanup_batch(
                    session,
                    model=model,
                    workspace_id=workspace_id,
                    cutoff=cutoff,
                    batch_size=batch_size,
                )
                if changed:
                    session.commit()
                    commits += 1
                elif session.in_transaction():
                    session.rollback()
                if label == "knowledge":
                    knowledge_candidates = candidates
                    knowledge_deleted = changed
                else:
                    intent_candidates = candidates
                    intents_expired = changed
            except Exception:
                if session.in_transaction():
                    session.rollback()
                log.error(
                    "guard.projection_retention.failed",
                    dry_run=False,
                    batch_size=batch_size,
                )
                raise
            finally:
                session.close()
        result = ProjectionRetentionResult(
            dry_run=False,
            knowledge_candidates=knowledge_candidates,
            knowledge_deleted=knowledge_deleted,
            intent_candidates=intent_candidates,
            intents_expired=intents_expired,
            batches_committed=commits,
            more_work=(
                knowledge_candidates == batch_size or intent_candidates == batch_size
            ),
        )

    aggregate = result.to_dict()
    log.info("guard.projection_retention.completed", **aggregate)
    if on_result is not None:
        on_result(aggregate)
    return result
