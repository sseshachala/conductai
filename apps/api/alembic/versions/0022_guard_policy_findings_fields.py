"""guard_policy findings vocabulary — recommendation, frameworks, severity, iso_control

Adds the four enterprise-vocabulary fields from #745 to guard_policies. JSONB pack
rules can carry the same keys; install_pack copies them into the SQL row.

Revision ID: 0022
Revises: 0021
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_policies", sa.Column("recommendation", sa.Text(), nullable=True))
    op.add_column(
        "guard_policies",
        sa.Column("frameworks", ARRAY(sa.Text()), nullable=False, server_default="{}"),
    )
    op.add_column(
        "guard_policies",
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
    )
    op.add_column("guard_policies", sa.Column("iso_control", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_policies", "iso_control")
    op.drop_column("guard_policies", "severity")
    op.drop_column("guard_policies", "frameworks")
    op.drop_column("guard_policies", "recommendation")
