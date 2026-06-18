import uuid
from datetime import datetime, timedelta, timezone
from math import log as math_log
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import SessionLocal, get_db
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
    developer_id: str | None = None
    developer_email: str | None = None


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
                "Extract: key decisions made, bugs found and how fixed, patterns discovered, gotchas. "
                "Even brief sessions are worth storing if any file was touched or any question was answered. "
                "Only return exactly NULL for sessions with zero code work (pure chat, no files, no tools). "
                "Otherwise return 1-5 sentences."
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


# Tools already handled by the CLI Stop hook — skip to avoid double-storing
_HOOK_TOOLS = {"claude_code", "claude-code"}
# Inactivity window: events >30 min apart = separate session
_SESSION_GAP = timedelta(minutes=30)


def _synthesize_mcp_sessions(workspace_id: str) -> None:
    """
    Background task: group recent MCP audit events into synthetic team memory sessions.
    Runs at most once per workspace per hour (guarded by a last-seen check).
    """
    db: Session = SessionLocal()
    try:
        ws_uuid = uuid.UUID(workspace_id)
        since = datetime.now(timezone.utc) - timedelta(hours=48)

        rows = db.execute(
            text("""
                SELECT hook_session_id, user_email, ai_tool, input_summary, ts
                FROM guard_audit_events
                WHERE workspace_id = :ws
                  AND ts >= :since
                  AND ai_tool IS NOT NULL
                  AND ai_tool != ALL(:skip_tools)
                  AND input_summary IS NOT NULL
                ORDER BY user_email, ai_tool, ts ASC
            """),
            {"ws": ws_uuid, "since": since, "skip_tools": list(_HOOK_TOOLS)},
        ).fetchall()

        if not rows:
            return

        # Group into sessions: by hook_session_id if present, else 30-min gap buckets
        sessions: dict[str, dict] = {}
        open_key: dict[tuple, str] = {}  # (email, tool) → current session key
        open_last_ts: dict[tuple, datetime] = {}

        for r in rows:
            bucket_key = (r.user_email or "", r.ai_tool)
            ts = r.ts if r.ts.tzinfo else r.ts.replace(tzinfo=timezone.utc)

            if r.hook_session_id:
                skey = f"mcp_{r.ai_tool}_{r.hook_session_id}"
            else:
                last_ts = open_last_ts.get(bucket_key)
                if last_ts is None or (ts - last_ts) > _SESSION_GAP:
                    skey = f"mcp_{r.ai_tool}_{r.user_email}_{ts.strftime('%Y%m%d%H%M')}"
                    open_key[bucket_key] = skey
                else:
                    skey = open_key[bucket_key]

            open_key[bucket_key] = skey
            open_last_ts[bucket_key] = ts

            if skey not in sessions:
                sessions[skey] = {
                    "session_id": skey,
                    "tool": r.ai_tool,
                    "user_email": r.user_email or "",
                    "summaries": [],
                }
            sessions[skey]["summaries"].append(r.input_summary)

        # Check which session_ids are already stored
        existing = {
            r[0] for r in db.execute(
                text("SELECT session_id FROM team_session_memory WHERE workspace_id = :ws"),
                {"ws": str(workspace_id)},
            ).fetchall()
        }

        for skey, meta in sessions.items():
            if skey in existing or len(meta["summaries"]) < 2:
                continue  # skip singletons and already-stored

            raw_transcript = "\n".join(f"- {s}" for s in meta["summaries"])
            summary = _summarise(raw_transcript)
            if not summary:
                continue

            tags = _extract_topic_tags(summary)
            embedding = _embed(summary)

            db.add(TeamSessionMemory(
                id=uuid.uuid4(),
                workspace_id=ws_uuid,
                developer_id=None,
                developer_email=meta["user_email"] or None,
                session_id=skey,
                tool=meta["tool"],
                repo_full_name=None,
                topic_tags=tags or None,
                light_summary=summary,
                files_touched=None,
                embedding=embedding,
                visibility="team",
            ))

        db.commit()
        log.info("team_memory.mcp_synthesized", workspace_id=workspace_id, candidates=len(sessions))
    except Exception as exc:
        log.warning("team_memory.mcp_synthesize_failed", error=str(exc))
    finally:
        db.close()


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

    # Resolve email at write time so the DEVELOPER column never shows a raw Clerk user ID
    resolved_email = body.developer_email
    if not resolved_email and body.developer_id:
        from app.core.auth import get_clerk_user_email
        resolved_email = get_clerk_user_email(body.developer_id) or None

    row = TeamSessionMemory(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(str(workspace_id)),
        developer_id=body.developer_id,
        developer_email=resolved_email,
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
    q: str | None = Query(default=None),
    repo: str | None = Query(default=None),
    limit: int = Query(default=5, ge=1, le=50),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> list[dict[str, Any]]:
    background_tasks.add_task(_synthesize_mcp_sessions, workspace_id)
    embedding = _embed(q) if q else None

    if embedding is not None:
        params: dict[str, Any] = {
            "workspace_id": str(workspace_id),
            "vec": str(embedding),
            "limit": limit * 3,
            "repo": repo,
        }

        rows = db.execute(
            text(
                "SELECT tsm.id, tsm.developer_id, COALESCE(u.email, tsm.developer_email) AS developer_email, "
                "tsm.repo_full_name, tsm.light_summary, tsm.topic_tags, "
                "tsm.tool, tsm.confidence, tsm.created_at, "
                "(tsm.embedding <=> CAST(:vec AS vector)) AS distance "
                "FROM team_session_memory tsm "
                "LEFT JOIN users u ON u.clerk_id = tsm.developer_id "
                "WHERE tsm.workspace_id = :workspace_id "
                "  AND tsm.visibility = 'team' "
                "  AND tsm.embedding IS NOT NULL "
                "  AND (:repo IS NULL OR tsm.repo_full_name = :repo) "
                "ORDER BY distance ASC "
                "LIMIT :limit"
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
            score = row.distance * (1.0 / math_log(days_ago + 2))
            scored.append((score, row))

        scored.sort(key=lambda x: x[0])
        rows = [r for _, r in scored[:limit]]

        return [
            {
                "developer_id": str(r.developer_id) if r.developer_id else None,
                "developer_email": r.developer_email or None,
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

    # Fallback: recency-based raw SQL (avoids ORM deserialising Vector column)
    fallback_params: dict[str, Any] = {
        "workspace_id": str(workspace_id),
        "limit": limit,
        "repo": repo,
    }

    rows_fallback = db.execute(
        text(
            "SELECT tsm.id, tsm.developer_id, COALESCE(u.email, tsm.developer_email) AS developer_email, "
            "tsm.repo_full_name, tsm.light_summary, tsm.topic_tags, "
            "tsm.tool, tsm.confidence, tsm.created_at "
            "FROM team_session_memory tsm "
            "LEFT JOIN users u ON u.clerk_id = tsm.developer_id "
            "WHERE tsm.workspace_id = :workspace_id "
            "  AND tsm.visibility = 'team' "
            "  AND (:repo IS NULL OR tsm.repo_full_name = :repo) "
            "ORDER BY tsm.created_at DESC "
            "LIMIT :limit"
        ),
        fallback_params,
    ).fetchall()

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


@router.delete("/sessions/unknown", status_code=200)
def delete_unknown_sessions(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> dict:
    """Delete all team memory rows with no developer_id for this workspace."""
    result = db.execute(
        text(
            "DELETE FROM team_session_memory "
            "WHERE workspace_id = :ws AND developer_id IS NULL"
        ),
        {"ws": workspace_id},
    )
    db.commit()
    return {"deleted": result.rowcount}
