"""GET /guard/knowledge/search — unified semantic search across Guard knowledge index."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.embedding import embedding_client_for_workspace

router = APIRouter(prefix="/guard/knowledge", tags=["guard"])


@router.get("/search")
def search_knowledge(
    q: str = Query(..., description="Natural language search query"),
    kind: str | None = Query(
        default=None,
        description="Optional filter: audit_event | rule | discovered_agent",
    ),
    limit: int = Query(default=10, ge=1, le=50),
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Semantic search across the Guard knowledge index.

    Returns ranked results from audit events, custom rules, and discovered agents.
    Score is cosine similarity (1.0 = identical, 0.0 = orthogonal).
    """
    db.rollback()
    client = embedding_client_for_workspace(workspace_id)
    if not client:
        raise HTTPException(status_code=503, detail="Embedding service not configured")

    embedding = client.embed(q[:2000])
    set_workspace_rls(db, workspace_id)
    kind_filter = "AND gki.source_kind = :kind" if kind else ""

    rows = db.execute(
        sa_text(
            f"SELECT gki.id, gki.source_kind, gki.source_id, gki.canonical_text, gki.metadata, "
            f"(gki.embedding <=> CAST(:vec AS vector)) AS distance "
            f"FROM guard_knowledge_index gki "
            f"WHERE gki.workspace_id = CAST(:workspace_id AS uuid) "
            f"  AND gki.embedding IS NOT NULL AND (gki.expires_at IS NULL OR gki.expires_at > now()) "
            f"{kind_filter} "
            f"ORDER BY distance ASC LIMIT :limit"
        ),
        {
            "workspace_id": workspace_id,
            "vec": str(embedding),
            "limit": limit,
            "kind": kind,
        },
    ).fetchall()

    return [
        {
            "id": str(r.id),
            "source_kind": r.source_kind,
            "source_id": r.source_id,
            "text": r.canonical_text,
            "metadata": r.metadata,
            "score": round(1 - r.distance, 3),
        }
        for r in rows
    ]
