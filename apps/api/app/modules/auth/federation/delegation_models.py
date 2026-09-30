"""Live local authorization records. Disabling a binding never removes it."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class FederationPrincipal(Base):
    __tablename__ = "federation_principals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    issuer = Column(String(512), nullable=False)
    subject = Column(String(512), nullable=False)
    display_name = Column(String(200), nullable=True)
    kind = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False)
    actions = Column(JSONB, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (
        UniqueConstraint("workspace_id", "issuer", "subject", name="uq_federation_principal_subject"),
        UniqueConstraint("workspace_id", "id", name="uq_federation_principal_workspace"),
    )


class FederationCallerBinding(Base):
    __tablename__ = "federation_caller_bindings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    caller_id = Column(String(36), nullable=False, unique=True)
    connection_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(16), nullable=False)
    actions = Column(JSONB, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "caller_id"],
                             ["agent_identities.workspace_id", "agent_identities.id"]),
        ForeignKeyConstraint(["workspace_id", "connection_id"],
                             ["federation_connections.workspace_id", "federation_connections.id"]),
        UniqueConstraint("workspace_id", "id", name="uq_federation_binding_workspace"),
    )


class FederationGrant(Base):
    __tablename__ = "federation_grants"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    binding_id = Column(UUID(as_uuid=True), nullable=False)
    principal_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(16), nullable=False)
    actions = Column(JSONB, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        ForeignKeyConstraint(["workspace_id", "binding_id"],
                             ["federation_caller_bindings.workspace_id", "federation_caller_bindings.id"]),
        ForeignKeyConstraint(["workspace_id", "principal_id"],
                             ["federation_principals.workspace_id", "federation_principals.id"]),
        UniqueConstraint("binding_id", "principal_id", name="uq_federation_grant_principal"),
    )
