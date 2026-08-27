"""SQLAlchemy model for cred_retrieval_tokens.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0071_cred_retrieval_tokens.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TEXT

from app.core.database import Base


class CredRetrievalToken(Base):
    __tablename__ = "cred_retrieval_tokens"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    token = sa.Column(sa.Text, nullable=False, unique=True)
    run_id = sa.Column(sa.Text, nullable=False)
    workspace_id = sa.Column(sa.Text, nullable=False)
    environment_id = sa.Column(sa.Text, nullable=True)
    allowed_handles = sa.Column(ARRAY(TEXT), nullable=False, server_default="{}")
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=False)
    created_at = sa.Column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    # Added by migration 0072 — rate limiting fields.
    used_count = sa.Column(sa.Integer, nullable=False, server_default="0")
    max_uses = sa.Column(sa.Integer, nullable=False, server_default="10")

    __table_args__ = (
        sa.Index("ix_cred_retrieval_tokens_token", "token"),
        sa.Index("ix_cred_retrieval_tokens_run_id", "run_id"),
    )
