"""Guard knowledge index — projectors and async indexing."""

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.models.workspace import Workspace
from app.modules.guard.embedding import embedding_client_for_workspace
from app.modules.guard.models import (
    DiscoveredAgent,
    GuardAuditEvent,
    GuardKnowledgeIndex,
    GuardProjectionIntent,
    GuardProjectionSummary,
    WorkspaceCustomRule,
)
from app.modules.guard.projection_contract import (
    ProjectionIntentStatus,
    ProjectionSourceKind,
)
from app.modules.guard.projection_policy import (
    audit_event_projection_reason,
    audit_event_source_version,
    projection_expires_at,
    projection_is_expired,
)

log = structlog.get_logger(__name__)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def _project_audit_event(event: GuardAuditEvent) -> tuple[str, dict]:
    """Build canonical text + metadata for an audit event."""
    parts = [
        f"Decision: {event.decision}",
        f"Tool: {event.tool_call or 'unknown'}",
        f"User: {event.user_email or 'unknown'}",
        f"AI tool: {event.ai_tool or 'unknown'}",
        f"Rule: {event.rule_id or 'none'}",
    ]
    if event.input_summary:
        parts.append(f"Input: {event.input_summary[:200]}")
    canonical = " | ".join(parts)
    metadata = {
        "decision": event.decision,
        "tool_name": event.tool_call,
        "user_email": event.user_email,
        "ai_tool": event.ai_tool,
        "rule_id": event.rule_id,
        "ts": event.ts.isoformat() if event.ts else None,
    }
    return canonical, metadata


def _project_rule(rule: WorkspaceCustomRule) -> tuple[str, dict]:
    """Build canonical text + metadata for a custom rule."""
    body = rule.body or {}
    parts = [
        f"Rule: {rule.rule_id}",
        f"Action: {body.get('action', 'unknown')}",
        f"Tool: {body.get('match_tool', '*')}",
        f"Description: {body.get('description', '')}",
        f"Pattern: {body.get('match_pattern', '')}",
        f"Severity: {body.get('severity', 'medium')}",
        f"Enabled: {rule.enabled}",
        f"Persona: {rule.persona}",
    ]
    canonical = " | ".join(p for p in parts if p.split(": ", 1)[1])
    metadata = {
        "rule_id": rule.rule_id,
        "action": body.get("action"),
        "match_tool": body.get("match_tool"),
        "enabled": rule.enabled,
        "persona": rule.persona,
        "severity": body.get("severity", "medium"),
    }
    return canonical, metadata


def _full_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@dataclass(frozen=True)
class _ProjectionSnapshot:
    workspace_id: str
    source_kind: ProjectionSourceKind
    source_id: str
    source_version: str
    canonical_text: str
    metadata: dict[str, Any]
    content_hash: str
    source_timestamp: datetime | None
    expires_at: datetime | None


def _project_audit_summary(summary: GuardProjectionSummary) -> tuple[str, dict]:
    metadata = dict(summary.canonical_facts or {})
    metadata.update(
        {
            "event_count": summary.event_count,
            "window_start": summary.window_start.isoformat(),
            "window_end": summary.window_end.isoformat(),
        }
    )
    rule_id = summary.rule_id or "none"
    canonical = " | ".join(
        [
            "Decision: allowed",
            f"AI tool: {summary.ai_tool}",
            f"Tool: {summary.tool_call}",
            f"Rule: {rule_id}",
            f"Events: {summary.event_count}",
            f"Window: {summary.window_start.isoformat()} to {summary.window_end.isoformat()}",
        ]
    )
    return canonical, metadata


def _version_candidates(
    source: Any, kind: ProjectionSourceKind, canonical: str, metadata: dict
) -> set[str]:
    versions = {_hash(canonical), _full_hash(canonical)}
    if kind is ProjectionSourceKind.AUDIT_EVENT:
        versions.add(audit_event_source_version(source))
    elif kind is ProjectionSourceKind.AUDIT_SUMMARY:
        versions.add(str(source.version))
    else:
        updated_at = getattr(source, "updated_at", None)
        if updated_at is not None:
            versions.add(updated_at.isoformat())
        versions.add(
            _full_hash(
                json.dumps(
                    {"text": canonical, "metadata": metadata},
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )
            )
        )
    return versions


def _load_source(
    db: Session,
    *,
    workspace_id: str,
    source_kind: ProjectionSourceKind,
    source_id: str,
    for_update: bool = False,
):
    ws_uuid = uuid.UUID(workspace_id)
    try:
        source_uuid = uuid.UUID(source_id)
    except ValueError:
        source_uuid = None
    query = None
    if source_kind is ProjectionSourceKind.AUDIT_EVENT and source_uuid:
        query = db.query(GuardAuditEvent).filter(
            GuardAuditEvent.id == source_uuid, GuardAuditEvent.workspace_id == ws_uuid
        )
    elif source_kind is ProjectionSourceKind.AUDIT_SUMMARY and source_uuid:
        query = db.query(GuardProjectionSummary).filter(
            GuardProjectionSummary.id == source_uuid,
            GuardProjectionSummary.workspace_id == ws_uuid,
        )
    elif source_kind is ProjectionSourceKind.RULE:
        query = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.rule_id == source_id,
            WorkspaceCustomRule.workspace_id == ws_uuid,
        )
    elif source_kind is ProjectionSourceKind.DISCOVERED_AGENT and source_uuid:
        query = db.query(DiscoveredAgent).filter(
            DiscoveredAgent.id == source_uuid, DiscoveredAgent.workspace_id == ws_uuid
        )
    if query is None:
        return None
    return (query.with_for_update() if for_update else query).first()


def _snapshot_source(
    source: Any,
    *,
    workspace_id: str,
    source_kind: ProjectionSourceKind,
    source_id: str,
    expected_version: str,
    now: datetime,
):
    if source_kind is ProjectionSourceKind.AUDIT_EVENT:
        if (
            audit_event_projection_reason(source.decision, source.evaluated_rules)
            is None
        ):
            return ProjectionIntentStatus.SUPERSEDED, None
        canonical, metadata = _project_audit_event(source)
        source_timestamp = source.ts
        expires_at = projection_expires_at(
            source_kind, source_timestamp, settings.guard_projection_retention_days
        )
    elif source_kind is ProjectionSourceKind.AUDIT_SUMMARY:
        canonical, metadata = _project_audit_summary(source)
        source_timestamp = source.source_timestamp
        expires_at = source.expires_at
    elif source_kind is ProjectionSourceKind.RULE:
        canonical, metadata = _project_rule(source)
        source_timestamp = expires_at = None
    elif source_kind is ProjectionSourceKind.DISCOVERED_AGENT:
        canonical, metadata = _project_discovered_agent(source)
        source_timestamp = expires_at = None
    else:
        return ProjectionIntentStatus.MISSING, None
    if expected_version not in _version_candidates(
        source, source_kind, canonical, metadata
    ):
        return ProjectionIntentStatus.SUPERSEDED, None
    if projection_is_expired(expires_at, now):
        return ProjectionIntentStatus.EXPIRED, None
    return None, _ProjectionSnapshot(
        workspace_id=workspace_id,
        source_kind=source_kind,
        source_id=source_id,
        source_version=expected_version,
        canonical_text=canonical,
        metadata=metadata,
        content_hash=_hash(canonical),
        source_timestamp=source_timestamp,
        expires_at=expires_at,
    )


def _intent_snapshot(intent_id: str):
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        intent_uuid = uuid.UUID(intent_id)
        intent = db.get(GuardProjectionIntent, intent_uuid)
        if intent is None:
            db.rollback()
            workspace_ids = [row.id for row in db.query(Workspace.id).all()]
            for candidate_workspace_id in workspace_ids:
                set_workspace_rls(db, candidate_workspace_id)
                intent = db.get(
                    GuardProjectionIntent, intent_uuid, populate_existing=True
                )
                if intent is not None:
                    break
                db.rollback()
        if intent is None:
            return ProjectionIntentStatus.MISSING, None
        workspace_id = str(intent.workspace_id)
        set_workspace_rls(db, workspace_id)
        intent = db.get(
            GuardProjectionIntent, uuid.UUID(intent_id), populate_existing=True
        )
        if intent is None:
            return ProjectionIntentStatus.MISSING, None
        if intent.status in {"completed", "superseded", "expired", "missing"}:
            return ProjectionIntentStatus(intent.status), None
        try:
            kind = ProjectionSourceKind(intent.source_kind)
        except ValueError:
            return ProjectionIntentStatus.MISSING, None
        source = _load_source(
            db, workspace_id=workspace_id, source_kind=kind, source_id=intent.source_id
        )
        if source is None:
            return ProjectionIntentStatus.MISSING, None
        return _snapshot_source(
            source,
            workspace_id=workspace_id,
            source_kind=kind,
            source_id=intent.source_id,
            expected_version=intent.source_version,
            now=now,
        )


def _projection_is_current(snapshot: _ProjectionSnapshot) -> bool:
    with SessionLocal() as db:
        set_workspace_rls(db, snapshot.workspace_id)
        row = (
            db.query(GuardKnowledgeIndex)
            .filter(
                GuardKnowledgeIndex.workspace_id == uuid.UUID(snapshot.workspace_id),
                GuardKnowledgeIndex.source_kind == snapshot.source_kind.value,
                GuardKnowledgeIndex.source_id == snapshot.source_id,
            )
            .first()
        )
        return bool(
            row
            and row.content_hash == snapshot.content_hash
            and row.meta == snapshot.metadata
            and row.source_timestamp == snapshot.source_timestamp
            and row.expires_at == snapshot.expires_at
            and row.embedding is not None
        )


def _conditional_write(
    snapshot: _ProjectionSnapshot,
    embedding: list[float],
    *,
    intent_id: str | None = None,
) -> ProjectionIntentStatus:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        set_workspace_rls(db, snapshot.workspace_id)
        if intent_id is not None:
            intent = db.get(GuardProjectionIntent, uuid.UUID(intent_id))
            if (
                intent is None
                or str(intent.workspace_id) != snapshot.workspace_id
                or intent.source_kind != snapshot.source_kind.value
                or intent.source_id != snapshot.source_id
                or intent.source_version != snapshot.source_version
            ):
                return ProjectionIntentStatus.MISSING
        source = _load_source(
            db,
            workspace_id=snapshot.workspace_id,
            source_kind=snapshot.source_kind,
            source_id=snapshot.source_id,
            for_update=True,
        )
        if source is None:
            return ProjectionIntentStatus.MISSING
        status, current = _snapshot_source(
            source,
            workspace_id=snapshot.workspace_id,
            source_kind=snapshot.source_kind,
            source_id=snapshot.source_id,
            expected_version=snapshot.source_version,
            now=now,
        )
        if status is not None or current is None:
            return status or ProjectionIntentStatus.MISSING
        stmt = (
            insert(GuardKnowledgeIndex)
            .values(
                workspace_id=uuid.UUID(current.workspace_id),
                source_kind=current.source_kind.value,
                source_id=current.source_id,
                canonical_text=current.canonical_text,
                meta=current.metadata,
                content_hash=current.content_hash,
                embedding=embedding,
                source_timestamp=current.source_timestamp,
                expires_at=current.expires_at,
                updated_at=now,
            )
            .on_conflict_do_update(
                constraint="guard_knowledge_index_workspace_id_source_kind_source_id_key",
                set_={
                    "canonical_text": current.canonical_text,
                    "metadata": current.metadata,
                    "content_hash": current.content_hash,
                    "embedding": embedding,
                    "source_timestamp": current.source_timestamp,
                    "expires_at": current.expires_at,
                    "updated_at": now,
                },
                where=sa.or_(
                    GuardKnowledgeIndex.content_hash != current.content_hash,
                    GuardKnowledgeIndex.meta.is_distinct_from(current.metadata),
                    GuardKnowledgeIndex.source_timestamp.is_distinct_from(
                        current.source_timestamp
                    ),
                    GuardKnowledgeIndex.expires_at.is_distinct_from(current.expires_at),
                ),
            )
        )
        db.execute(stmt)
        db.commit()
    log.debug(
        "guard.knowledge.indexed",
        source_kind=snapshot.source_kind.value,
        source_id=snapshot.source_id,
    )
    return ProjectionIntentStatus.COMPLETED


def process_projection_intent(intent_id: str) -> ProjectionIntentStatus:
    """Process one intent without holding a connection during the provider call."""
    status, snapshot = _intent_snapshot(intent_id)
    if status is not None or snapshot is None:
        return status or ProjectionIntentStatus.MISSING
    if _projection_is_current(snapshot):
        return ProjectionIntentStatus.COMPLETED
    client = embedding_client_for_workspace(snapshot.workspace_id)
    if not client:
        raise RuntimeError("Embedding service not configured")
    embedding = client.embed(snapshot.canonical_text[:2000])
    return _conditional_write(snapshot, embedding, intent_id=intent_id)


def index_source(
    workspace_id: str,
    source_kind: str,
    source_id: str,
    canonical_text: str,
    metadata: dict,
    db: Session,
) -> None:
    """Preserve the legacy API while detaching the provider wait."""
    kind = ProjectionSourceKind(source_kind)
    source = _load_source(
        db, workspace_id=workspace_id, source_kind=kind, source_id=source_id
    )
    if source is None:
        return
    source_version = (
        audit_event_source_version(source)
        if kind is ProjectionSourceKind.AUDIT_EVENT
        else str(source.version)
        if kind is ProjectionSourceKind.AUDIT_SUMMARY
        else _hash(canonical_text)
    )
    status, snapshot = _snapshot_source(
        source,
        workspace_id=workspace_id,
        source_kind=kind,
        source_id=source_id,
        expected_version=source_version,
        now=datetime.now(timezone.utc),
    )
    if status is not None or snapshot is None:
        return
    db.commit()
    if _projection_is_current(snapshot):
        return
    client = embedding_client_for_workspace(workspace_id)
    if not client:
        log.warning("guard.knowledge.no_embedding_client", workspace_id=workspace_id)
        return
    embedding = client.embed(snapshot.canonical_text[:2000])
    _conditional_write(snapshot, embedding)


def project_audit_event(event: GuardAuditEvent, db: Session) -> None:
    """Project a GuardAuditEvent into the knowledge index."""
    canonical, metadata = _project_audit_event(event)
    index_source(
        str(event.workspace_id), "audit_event", str(event.id), canonical, metadata, db
    )


def project_rule(rule: WorkspaceCustomRule, db: Session) -> None:
    """Project a WorkspaceCustomRule into the knowledge index."""
    canonical, metadata = _project_rule(rule)
    index_source(str(rule.workspace_id), "rule", rule.rule_id, canonical, metadata, db)


def _project_discovered_agent(agent: DiscoveredAgent) -> tuple[str, dict]:
    from app.modules.guard.discovery_inventory import agent_view

    view = agent_view(agent)
    # Indexed facts must not turn into indefinitely cached protection claims.
    metadata = {key: view[key] for key in ("id", "framework", "device_id", "detection")}
    return (
        f"Discovery finding: {agent.framework}. Query live discovery inventory for protection and freshness evidence.",
        metadata,
    )


def project_discovered_agent(agent: DiscoveredAgent, db: Session) -> None:
    """Project a DiscoveredAgent into the knowledge index."""
    canonical, metadata = _project_discovered_agent(agent)
    index_source(
        str(agent.workspace_id),
        "discovered_agent",
        str(agent.id),
        canonical,
        metadata,
        db,
    )
