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
    # Aggregate-only result safe for logs, callbacks, and workers.
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


def cleanup_expired_projections(
    db: Session,
    *,
    workspace_id: Any | None = None,
    batch_size: int = DEFAULT_RETENTION_BATCH_SIZE,
    dry_run: bool = False,
    now: datetime | None = None,
    model_overrides: Mapping[str, Any] | None = None,
) -> ProjectionRetentionResult:
    # Run one bounded pass, committing each non-empty batch separately.
    if isinstance(batch_size, bool) or not isinstance(batch_size, int):
        raise TypeError("batch_size must be a positive integer")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")

    knowledge_model, intent_model = _resolve_models(model_overrides)
    cutoff = now if now is not None else func.now()
    knowledge_predicates: tuple[Any, ...] = ()
    intent_predicates: tuple[Any, ...] = ()
    if knowledge_model is not None:
        _validate_model(
            knowledge_model,
            ("id", "workspace_id", "source_kind", "expires_at"),
            "knowledge",
        )
        knowledge_predicates = _knowledge_predicates(
            knowledge_model, workspace_id, cutoff
        )
    if intent_model is not None:
        _validate_model(
            intent_model,
            ("id", "workspace_id", "source_kind", "status", "expires_at"),
            "intent",
        )
        intent_predicates = _intent_predicates(intent_model, workspace_id, cutoff)

    if dry_run:
        knowledge_count = (
            _count_candidates(db, knowledge_model, knowledge_predicates)
            if knowledge_model is not None
            else 0
        )
        intent_count = (
            _count_candidates(db, intent_model, intent_predicates)
            if intent_model is not None
            else 0
        )
        return ProjectionRetentionResult(
            dry_run=True,
            knowledge_candidates=knowledge_count,
            intent_candidates=intent_count,
        )

    knowledge_ids: list[Any] = []
    intent_ids: list[Any] = []
    knowledge_deleted = 0
    intents_expired = 0
    commits = 0
    try:
        if knowledge_model is not None:
            knowledge_ids = _candidate_ids(
                db, knowledge_model, knowledge_predicates, batch_size
            )
            if knowledge_ids:
                result = db.execute(
                    delete(knowledge_model)
                    .where(
                        knowledge_model.id.in_(knowledge_ids),
                        *_knowledge_predicates(knowledge_model, workspace_id, cutoff),
                    )
                    .execution_options(synchronize_session=False)
                )
                knowledge_deleted = result.rowcount or 0
                db.commit()
                commits += 1
        if intent_model is not None:
            intent_ids = _candidate_ids(db, intent_model, intent_predicates, batch_size)
            if intent_ids:
                result = db.execute(
                    update(intent_model)
                    .where(
                        intent_model.id.in_(intent_ids),
                        *_intent_predicates(intent_model, workspace_id, cutoff),
                    )
                    .values(status=ProjectionIntentStatus.EXPIRED.value)
                    .execution_options(synchronize_session=False)
                )
                intents_expired = result.rowcount or 0
                db.commit()
                commits += 1
    except Exception:
        db.rollback()
        log.error(
            "guard.projection_retention.failed", dry_run=False, batch_size=batch_size
        )
        raise

    return ProjectionRetentionResult(
        dry_run=False,
        knowledge_candidates=len(knowledge_ids),
        knowledge_deleted=knowledge_deleted,
        intent_candidates=len(intent_ids),
        intents_expired=intents_expired,
        batches_committed=commits,
        more_work=(len(knowledge_ids) == batch_size or len(intent_ids) == batch_size),
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
    # Worker-callable pass with aggregate-only logging and callback data.
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

    owns_session = db is None
    if db is None:
        if session_factory is None:
            from app.core.database import SessionLocal

            session_factory = SessionLocal
        db = session_factory()
    try:
        result = cleanup_expired_projections(
            db,
            workspace_id=workspace_id,
            batch_size=batch_size,
            dry_run=dry_run,
            now=now,
            model_overrides=model_overrides,
        )
        aggregate = result.to_dict()
        log.info("guard.projection_retention.completed", **aggregate)
        if on_result is not None:
            on_result(aggregate)
        return result
    finally:
        if owns_session:
            db.close()
