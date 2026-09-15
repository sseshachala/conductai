"""Add route column to guard_audit_events.

Follow-up to #1971 (Phase 0 of #1959). Records the FastAPI request path
(e.g. /proxy/anthropic/v1/messages vs /gateway/v1/anthropic/v1/messages)
so legacy vs new Gateway traffic is queryable directly from audit rows
instead of requiring a Render-logs excursion.

Nullable — historical rows and in-process callers (guard/gateway.py::
guarded_*) stay NULL. Indexed so ``WHERE route LIKE '/proxy/%'`` scans
stay cheap once the tail of legacy hits shrinks to zero.

Revision ID: 0131
Revises: 0130
"""
from alembic import op
import sqlalchemy as sa


revision = "0131"
down_revision = "0130"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_audit_events",
        sa.Column("route", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_guard_audit_events_route",
        "guard_audit_events",
        ["route"],
    )


def downgrade():
    op.drop_index("ix_guard_audit_events_route", table_name="guard_audit_events")
    op.drop_column("guard_audit_events", "route")
