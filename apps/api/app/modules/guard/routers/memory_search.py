"""GET /guard/memory/search — semantic search over team memory for GLens."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.embedding import embedding_client_for_workspace

router = APIRouter(prefix="/guard/memory", tags=["guard"])


@router.get("/search")
def search_memory(
    q: str = Query(..., description="Natural language search query"),
    limit: int = Query(default=5, ge=1, le=20),
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Semantic search over team session memory using pgvector."""
    client = embedding_client_for_workspace(db, workspace_id)
    if not client:
        raise HTTPException(status_code=503, detail="Embedding service not configured")

    embedding = client.embed(q[:2000])
    rows = db.execute(
        sa_text(
            "SELECT tsm.id, tsm.developer_email, tsm.light_summary, tsm.topic_tags, "
            "tsm.repo_full_name, tsm.created_at, "
            "(tsm.embedding <=> CAST(:vec AS vector)) AS distance "
            "FROM team_session_memory tsm "
            "WHERE tsm.workspace_id = :workspace_id "
            "  AND tsm.visibility = 'team' "
            "  AND tsm.embedding IS NOT NULL "
            "ORDER BY distance ASC LIMIT :limit"
        ),
        {"workspace_id": workspace_id, "vec": str(embedding), "limit": limit},
    ).fetchall()

    return [
        {
            "id": str(r.id),
            "developer_email": r.developer_email,
            "summary": r.light_summary,
            "topic_tags": r.topic_tags or [],
            "repo": r.repo_full_name,
            "created_at": r.created_at.isoformat(),
            "score": round(1 - r.distance, 3),
        }
        for r in rows
    ]
