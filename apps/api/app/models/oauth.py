"""OAuth 2.1 SQLAlchemy models (migration 0118)."""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class OauthClient(Base):
    __tablename__ = "oauth_clients"

    client_id                   = Column(Text, primary_key=True)
    client_name                 = Column(Text, nullable=False)
    redirect_uris               = Column(JSONB, nullable=False)  # list[str], exact match
    grant_types                 = Column(JSONB, nullable=False,
                                         server_default=text("'[\"authorization_code\", \"refresh_token\"]'::jsonb"))
    token_endpoint_auth_method  = Column(Text, nullable=False, server_default="none")
    scope                       = Column(Text, nullable=True)
    created_by_clerk_user_id    = Column(Text, nullable=True)
    created_at                  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at                  = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class OauthAuthCode(Base):
    __tablename__ = "oauth_auth_codes"

    id                     = Column(UUID(as_uuid=True), primary_key=True)
    code_hash              = Column(Text, nullable=True)  # sha256; NULL until /confirm
    client_id              = Column(Text, ForeignKey("oauth_clients.client_id", name="fk_oauth_auth_codes_client"), nullable=False)
    redirect_uri           = Column(Text, nullable=False)
    code_challenge         = Column(Text, nullable=False)
    code_challenge_method  = Column(Text, nullable=False, server_default="S256")
    state                  = Column(Text, nullable=False)
    scope                  = Column(Text, nullable=True)
    clerk_user_id          = Column(Text, nullable=True)
    workspace_id           = Column(UUID(as_uuid=True), nullable=True)
    status                 = Column(Text, nullable=False, server_default="pending")
    created_at             = Column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    expires_at             = Column(DateTime(timezone=True), nullable=False)
    used_at                = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'issued', 'consumed')",
                        name="ck_oauth_auth_codes_status"),
        Index("ix_oauth_auth_codes_code_hash", "code_hash",
              unique=True, postgresql_where=text("code_hash IS NOT NULL")),
        Index("ix_oauth_auth_codes_expires_at", "expires_at"),
    )
