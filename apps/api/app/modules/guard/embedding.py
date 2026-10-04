"""Shared embedding helper for Guard modules."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from app.core.credentials import get_credential
from app.core.database import SessionLocal
from app.core.workspace_context import set_workspace_rls
from app.runtime.embedding_client import EmbeddingClient, create_embedding_client


def embedding_client_for_workspace(
    workspace_or_session: str | Session,
    workspace_id: str | None = None,
    *,
    db_factory: Callable[[], Session] = SessionLocal,
) -> EmbeddingClient | None:
    """Resolve credentials in a short owned session and return a detached client."""
    resolved_workspace_id = (
        str(workspace_id) if workspace_id is not None else str(workspace_or_session)
    )
    db = db_factory()
    try:
        set_workspace_rls(db, resolved_workspace_id)
        env = get_credential(db, resolved_workspace_id, "env_vars")
    finally:
        try:
            db.rollback()
        finally:
            db.close()

    return create_embedding_client(
        openai_api_key=env.get("OPENAI_API_KEY") or env.get("openai_api_key"),
        voyage_api_key=env.get("VOYAGE_API_KEY") or env.get("voyage_api_key"),
    )
