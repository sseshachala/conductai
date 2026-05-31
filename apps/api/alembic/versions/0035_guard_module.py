"""add ConductGuard module tables

Revision ID: 0035
Revises: 0034
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "guard_teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("invite_code", sa.String(32), nullable=False, unique=True),
        sa.Column("conductai_workspace_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "guard_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("guard_teams.id"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="developer"),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "guard_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("guard_teams.id"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("match_tool", sa.String(255), nullable=True),
        sa.Column("match_pattern", sa.String(500), nullable=True),
        sa.Column("match_path_pattern", sa.String(500), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("builtin", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "guard_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("guard_teams.id"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("guard_members.id"), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("ai_tool", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tokens_before", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_tokens_after", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("total_saved_usd", sa.Float, nullable=False, server_default="0.0"),
        sa.Column("event_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("violations_count", sa.Integer, nullable=False, server_default="0"),
    )

    op.create_table(
        "guard_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("guard_teams.id"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("guard_members.id"), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("guard_sessions.id"), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("ai_tool", sa.String(50), nullable=False),
        sa.Column("tool_call", sa.String(50), nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=True),
        sa.Column("rule_message", sa.Text, nullable=True),
        sa.Column("tokens_before", sa.Integer, nullable=True),
        sa.Column("tokens_after", sa.Integer, nullable=True),
        sa.Column("tokens_saved", sa.Integer, nullable=True),
        sa.Column("cost_usd_before", sa.Float, nullable=True),
        sa.Column("cost_usd_after", sa.Float, nullable=True),
        sa.Column("conductai_run_id", sa.String(255), nullable=True),
        sa.Column("conductai_workflow", sa.String(255), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )

    op.create_table(
        "guard_spend_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("team_id", UUID(as_uuid=True), sa.ForeignKey("guard_teams.id"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("guard_members.id"), nullable=True),
        sa.Column("monthly_limit_usd", sa.Float, nullable=False),
        sa.Column("alert_threshold_pct", sa.Integer, nullable=False, server_default="80"),
        sa.Column("hard_limit_usd", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade():
    op.drop_table("guard_spend_budgets")
    op.drop_table("guard_audit_events")
    op.drop_table("guard_sessions")
    op.drop_table("guard_policies")
    op.drop_table("guard_members")
    op.drop_table("guard_teams")
