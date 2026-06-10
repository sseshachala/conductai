import uuid
from datetime import datetime, timezone
from math import log
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.models.team_session_memory import TeamSessionMemory

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/team-memory", tags=["team-memory"])

_TECH_KEYWORDS = [
    "auth", "jwt", "oauth", "token", "database", "db", "postgres", "redis",
    "api", "rest", "graphql", "deploy", "docker", "kubernetes", "migration",
    "index", "cache", "queue", "webhook", "cors", "ssl", "tls", "encryption",
    "test", "ci", "pipeline", "build", "lint", "schema", "model", "orm",
    "async", "worker", "celery", "fastapi", "react", "typescript", "python",
    "bug", "fix", "refactor", "performance", "memory", "leak", "timeout",
    "rate limit", "retry", "circuit breaker", "logging", "tracing",
]


class SessionMemoryIn(BaseModel):
    session_id: str
    tool: str = "claude_code"
    repo_full_name: str | None = None
    raw_transcript: str | None = None
    files_touched: list[str] = []
    visibility: str = "team"


def _extract_topic_tags(text_content: str) -> list[str]:
    lower = text_content.lower()
    return [kw for kw in _TECH_KEYWORDS if kw in lower]


def _summarise(raw_transcript: str | None) -> str | None:
    from app.core.config import settings

    if not raw_transcript:
        return None

    truncated = raw_transcript[:8000]

    if not settings.anthropic_api_key:
        return truncated[:500]

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            system=(
                "You are extracting team-useful learnings from an AI coding session. "
                "Extract: key decisions made, bugs found and how fixed, architectural patterns "
                "discovered, gotchas encountered. If the session contains no team-useful findings "
                "(pure exploration, no decisions), return exactly: NULL. "
                "Otherwise return 2-5 sentences max."
            ),
            messages=[{"role": "user", "content": truncated}],
        )
        result = msg.content[0].text.strip()
        if result == "NULL" or not result:
            return None
        return result
    except Exception as exc:
        log.warning("team_memory.summarise_failed", error=str(exc))
        return truncated[:500]


def _embed(text_content: str) -> list[float] | None:
    try:
        from app.runtime.embedding_client import create_embedding_client
        client = create_embedding_client()
        if client is None:
            return None
        return client.embed(text_content)
    except Exception as exc:
        log.warning("team_memory.embed_failed", error=str(exc))
        return None


@router.post("/sessions", status_code=201)
def store_session_memory(
    body: SessionMemoryIn,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    summary = _summarise(body.raw_transcript)
    if summary is None:
        return {"stored": False, "reason": "no_findings"}

    tags = _extract_topic_tags(summary)
    embedding = _embed(summary)

    row = TeamSessionMemory(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(workspace_id),
        developer_id=None,
        session_id=body.session_id,
        tool=body.tool,
        repo_full_name=body.repo_full_name,
        topic_tags=tags or None,
        light_summary=summary,
        files_touched=body.files_touched or None,
        embedding=embedding,
        visibility=body.visibility,
    )
    db.add(row)
    db.commit()

    log.info(
        "team_memory.stored",
        workspace_id=workspace_id,
        session_id=body.session_id,
        summary_chars=len(summary),
        has_embedding=embedding is not None,
    )

    return {"stored": True, "session_id": body.session_id, "summary_chars": len(summary)}


@router.get("/search")
def search_session_memory(
    q: str = Query(..., min_length=1),
    repo: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=50),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    embedding = _embed(q)

    if embedding is not None:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "vec": str(embedding),
            "limit": limit * 3,
        }
        filters = "workspace_id = :workspace_id AND visibility = 'team' AND embedding IS NOT NULL"
        if repo:
            filters += " AND repo_full_name = :repo"
            params["repo"] = repo

        rows = db.execute(
            text(
                f"SELECT id, developer_id, repo_full_name, light_summary, topic_tags, "
                f"tool, confidence, created_at, "
                f"(embedding <=> CAST(:vec AS vector)) AS distance "
                f"FROM team_session_memory "
                f"WHERE {filters} "
                f"ORDER BY distance ASC "
                f"LIMIT :limit"
            ),
            params,
        ).fetchall()

        now = datetime.now(timezone.utc)
        scored: list[tuple[float, Any]] = []
        for row in rows:
            created_at = row.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            days_ago = max(0.0, (now - created_at).total_seconds() / 86400)
            score = row.distance * (1.0 / log(days_ago + 2))
            scored.append((score, row))

        scored.sort(key=lambda x: x[0])
        rows = [r for _, r in scored[:limit]]

        return [
            {
                "developer_id": str(r.developer_id) if r.developer_id else None,
                "repo": r.repo_full_name,
                "summary": r.light_summary,
                "tags": r.topic_tags or [],
                "tool": r.tool,
                "confidence": r.confidence,
                "created_at": r.created_at.isoformat(),
                "distance": round(r.distance, 4),
            }
            for r in rows
        ]

    # Fallback: recency-based query (no embedding available)
    query = db.query(TeamSessionMemory).filter(
        TeamSessionMemory.workspace_id == uuid.UUID(workspace_id),
        TeamSessionMemory.visibility == "team",
    )
    if repo:
        query = query.filter(TeamSessionMemory.repo_full_name == repo)

    rows_fallback = query.order_by(TeamSessionMemory.created_at.desc()).limit(limit).all()

    return [
        {
            "developer_id": str(r.developer_id) if r.developer_id else None,
            "repo": r.repo_full_name,
            "summary": r.light_summary,
            "tags": r.topic_tags or [],
            "tool": r.tool,
            "confidence": r.confidence,
            "created_at": r.created_at.isoformat(),
            "distance": None,
        }
        for r in rows_fallback
    ]
