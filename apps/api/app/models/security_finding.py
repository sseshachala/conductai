import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SecurityFinding(Base):
    __tablename__ = "security_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String, nullable=False, index=True)
    tool = Column(String, nullable=False)           # claude-code | codex | cursor | copilot | manual
    severity = Column(String, nullable=False)       # critical | high | medium | low | info
    type = Column(String, nullable=False)           # injection | path-traversal | secret-leak | auth-bypass | crypto | other
    file = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    suggested_fix = Column(Text, nullable=True)
    repo_full_name = Column(String, nullable=True, index=True)
    commit_sha = Column(String, nullable=True)
    source_run_id = Column(String, nullable=True)   # optional — if surfaced inside a Conduct run
    status = Column(String, nullable=False, default="open")  # open | triaging | fixed | dismissed
    github_issue_url = Column(String, nullable=True)
    run_id = Column(String, nullable=True)          # Security Loop pipeline run that handled this
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
