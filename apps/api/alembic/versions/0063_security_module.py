"""feat(secure): security_config + security_policies tables; drop security cols from guard_config

Revision ID: 0063
Revises: 0062
Create Date: 2026-06-07
"""
import uuid as _uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0063"
down_revision = "0062"
branch_labels = None
depends_on = None

_BUILTIN_POLICIES = [
    ("secret-sk-key",      r"sk-[A-Za-z0-9]{20,}",     "secret-leak",    "high",     "OpenAI/Anthropic API key pattern"),
    ("secret-gh-pat",      r"ghp_[A-Za-z0-9]{36}",     "secret-leak",    "high",     "GitHub Personal Access Token"),
    ("secret-aws-key",     r"AKIA[0-9A-Z]{16}",         "secret-leak",    "critical", "AWS Access Key ID"),
    ("secret-password",    r"password\s*=\s*[^\s]{4,}", "secret-leak",    "high",     "Hardcoded password"),
    ("secret-api-key",     r"api_?key\s*=\s*[^\s]{4,}", "secret-leak",    "high",     "Hardcoded API key"),
    ("path-traversal",     r"\.\./\.\./\.\./",           "path-traversal", "medium",   "Path traversal sequence"),
    ("code-eval",          r"\beval\s*\(",               "injection",      "high",     "eval() in code"),
    ("ssl-cert-none",      r"ssl\.CERT_NONE",            "crypto",         "high",     "SSL certificate verification disabled"),
    ("tls-verify-false",   r"verify\s*=\s*False",        "crypto",         "medium",   "TLS verification bypassed"),
]


def upgrade() -> None:
    op.create_table(
        "security_config",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("installed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("security_emit_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("security_slack_alerts_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("security_slack_channel", sa.String(100), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "security_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("pattern", sa.String(500), nullable=True),
        sa.Column("finding_type", sa.String(50), nullable=False, server_default="other"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_security_policies_workspace", "security_policies", ["workspace_id"])

    # Drop security columns migrated from guard_config (added in 0062)
    op.drop_column("guard_config", "security_emit_enabled")
    op.drop_column("guard_config", "security_slack_alerts_enabled")
    op.drop_column("guard_config", "security_slack_channel")


def downgrade() -> None:
    op.drop_index("ix_security_policies_workspace", table_name="security_policies")
    op.drop_table("security_policies")
    op.drop_table("security_config")

    op.add_column("guard_config", sa.Column("security_emit_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("guard_config", sa.Column("security_slack_alerts_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("guard_config", sa.Column("security_slack_channel", sa.String(100), nullable=True))
