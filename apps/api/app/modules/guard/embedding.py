"""Shared embedding helper for Guard modules."""
from sqlalchemy.orm import Session

from app.core.credentials import get_credential
from app.runtime.embedding_client import EmbeddingClient, create_embedding_client


def embedding_client_for_workspace(db: Session, workspace_id: str) -> EmbeddingClient | None:
    env = get_credential(db, workspace_id, "env_vars")
    return create_embedding_client(
        openai_api_key=env.get("OPENAI_API_KEY") or env.get("openai_api_key"),
        voyage_api_key=env.get("VOYAGE_API_KEY") or env.get("voyage_api_key"),
    )
