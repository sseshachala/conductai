"""guard shadow agent discovery tables

Revision ID: 0044
Revises: 0043
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "discovery_scans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("triggered_by", sa.String(20), nullable=False),   # cli | schedule
        sa.Column("status", sa.String(20), nullable=False),          # running | complete | failed
        sa.Column("agents_found", sa.Integer, nullable=True),
        sa.Column("guard_coverage", sa.Integer, nullable=True),       # count under Guard
        sa.Column("scan_config", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_discovery_scans_workspace", "discovery_scans", ["workspace_id"])

    op.create_table(
        "discovered_agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scan_id", UUID(as_uuid=True), sa.ForeignKey("discovery_scans.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.Text, nullable=True),
        sa.Column("framework", sa.String(50), nullable=True),   # langchain|crewai|autogen|claude-code|copilot|cursor|codex|windsurf|openai-agents
        sa.Column("source", sa.String(20), nullable=True),      # config | process | github
        sa.Column("location", sa.Text, nullable=True),          # config path | process cmd
        sa.Column("evidence", JSONB, nullable=True),
        sa.Column("risk_score", sa.Integer, nullable=True),     # 0-100
        sa.Column("under_guard", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_discovered_agents_workspace", "discovered_agents", ["workspace_id"])
    op.create_index("ix_discovered_agents_scan", "discovered_agents", ["scan_id"])


def downgrade():
    op.drop_table("discovered_agents")
    op.drop_table("discovery_scans")
