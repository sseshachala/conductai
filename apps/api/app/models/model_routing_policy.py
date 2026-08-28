"""SQLAlchemy model for model_routing_policies.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0007_model_routing_policies.py.
"""
from __future__ import annotations

import sqlalchemy as sa

from app.core.database import Base


class ModelRoutingPolicy(Base):
    __tablename__ = "model_routing_policies"

    id = sa.Column(sa.Integer(), primary_key=True, autoincrement=True)
    category = sa.Column(sa.Text(), nullable=False, server_default="")
    preference = sa.Column(sa.Text(), nullable=False)
    provider = sa.Column(sa.Text(), nullable=False)
    model_id = sa.Column(sa.Text(), nullable=False)
    reason = sa.Column(sa.Text(), nullable=False, server_default="")
    enabled = sa.Column(sa.Boolean(), nullable=False, server_default="true")

    __table_args__ = (
        sa.UniqueConstraint("category", "preference", name="uq_routing_category_preference"),
    )
