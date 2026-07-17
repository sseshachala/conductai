"""Guard knowledge index — projectors and async indexing."""
import hashlib
import uuid
from datetime import datetime, timezone

import structlog
from sqlalchemy.orm import Session

from app.modules.guard.embedding import embedding_client_for_workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardKnowledgeIndex,
    WorkspaceCustomRule,
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


def index_source(
    workspace_id: str,
    source_kind: str,
    source_id: str,
    canonical_text: str,
    metadata: dict,
    db: Session,
) -> None:
    """Upsert one document into guard_knowledge_index with embedding."""
    content_hash = _hash(canonical_text)
    ws_uuid = uuid.UUID(workspace_id)

    existing = (
        db.query(GuardKnowledgeIndex)
        .filter(
            GuardKnowledgeIndex.workspace_id == ws_uuid,
            GuardKnowledgeIndex.source_kind == source_kind,
            GuardKnowledgeIndex.source_id == source_id,
        )
        .first()
    )

    if existing and existing.content_hash == content_hash:
        return  # unchanged — skip re-embedding

    client = embedding_client_for_workspace(db, workspace_id)
    if not client:
        log.warning("guard.knowledge.no_embedding_client", workspace_id=workspace_id)
        return

    embedding = client.embed(canonical_text[:2000])

    if existing:
        existing.canonical_text = canonical_text
        existing.metadata = metadata
        existing.content_hash = content_hash
        existing.embedding = embedding
        existing.updated_at = datetime.now(timezone.utc)
    else:
        db.add(
            GuardKnowledgeIndex(
                workspace_id=ws_uuid,
                source_kind=source_kind,
                source_id=source_id,
                canonical_text=canonical_text,
                metadata=metadata,
                content_hash=content_hash,
                embedding=embedding,
            )
        )
    db.commit()
    log.debug(
        "guard.knowledge.indexed",
        source_kind=source_kind,
        source_id=source_id,
    )


def project_audit_event(event: GuardAuditEvent, db: Session) -> None:
    """Project a GuardAuditEvent into the knowledge index."""
    canonical, metadata = _project_audit_event(event)
    index_source(str(event.workspace_id), "audit_event", str(event.id), canonical, metadata, db)


def project_rule(rule: WorkspaceCustomRule, db: Session) -> None:
    """Project a WorkspaceCustomRule into the knowledge index."""
    canonical, metadata = _project_rule(rule)
    index_source(str(rule.workspace_id), "rule", rule.rule_id, canonical, metadata, db)
