"""guard_rule_overrides.match_pattern — allow overriding regex per workspace

Revision ID: 0036_guard_rule_override_match_pattern
Revises: 0035_integrations_environment_id_nullable
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0036_guard_rule_override_match_pattern"
down_revision = "0035_integrations_environment_id_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_rule_overrides", sa.Column("match_pattern", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("guard_rule_overrides", "match_pattern")
