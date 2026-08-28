import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class McpServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE", name="mcp_servers_workspace_id_fkey"),
        nullable=False,
    )
    environment_id = Column(
        UUID(as_uuid=True),
        ForeignKey("environments.id", ondelete="SET NULL", name="mcp_servers_environment_id_fkey"),
        nullable=True,
    )
    name = Column(String, nullable=False)
    url = Column(Text, nullable=False)
    transport = Column(String, nullable=False, default="http")
    encrypted_auth = Column(Text, nullable=True)
    is_system = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_mcp_server_name_per_workspace"),
    )
