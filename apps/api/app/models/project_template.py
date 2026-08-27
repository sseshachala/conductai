"""SQLAlchemy model for project_templates.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0001_baseline.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

from app.core.database import Base


class ProjectTemplate(Base):
    __tablename__ = "project_templates"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    slug = sa.Column(sa.String(100), nullable=False, unique=True)
    name = sa.Column(sa.String(255), nullable=False)
    description = sa.Column(sa.Text, nullable=False)
    default_mode = sa.Column(sa.String(50), nullable=False, server_default="dag")
    nodes = sa.Column(JSONB, nullable=False, server_default="[]")
    edges = sa.Column(JSONB, nullable=False, server_default="[]")
