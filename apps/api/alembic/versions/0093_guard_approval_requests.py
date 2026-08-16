"""Guard approval requests — HITL flow for action=approval (#1140).

Introduces `guard_approval_requests` — one row per pause requested by a
Guard rule with action=approval. Surface-agnostic: created from the CLI/MCP
hook, LLM proxy, or workflow runtime. When the trigger is inside a workflow
run, we ALSO emit approval_requested / approval_received run_events so the
existing DSL-approve resume path keeps working.

Also seeds a new permission `platform.approvals.decide` (admin + security).

Revision ID: 0093
Revises: 0092
Create Date: 2026-08-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "0093"
down_revision = "0092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_approval_requests",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Which policy rule triggered this pause.
        sa.Column("rule_id", sa.String(200), nullable=False),
        sa.Column("rule_pack", sa.String(100), nullable=True),
        sa.Column("rule_message", sa.Text, nullable=True),
        # Redacted snapshot of the tool call that triggered the rule.
        sa.Column("tool_name", sa.String(100), nullable=True),
        sa.Column("tool_input", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        # Who asked. requester_email may be empty for agent-only tokens.
        sa.Column("requester_email", sa.String(255), nullable=True),
        sa.Column("requester_user_id", sa.String(255), nullable=True),
        sa.Column("requester_agent_ident", sa.String(255), nullable=True),
        # Where it came from. Surface labels align with _detect_surface() in guard/mcp.py.
        sa.Column("surface", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("session_id", sa.String(255), nullable=True),
        # Workflow-run linkage — nullable; set when the guard block inside a workflow
        # created the request. Lets the decide endpoint resume the run.
        sa.Column("source_run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_block_id", sa.String(255), nullable=True),
        # Who can decide.
        sa.Column("approval_group", sa.String(100), nullable=True),
        # peer      = requester_email must != decider_email (2-person rule)
        # any_admin = any workspace admin
        # any_security = admin OR security
        # any_authorized = anyone with platform.approvals.decide (default)
        sa.Column("approval_type", sa.String(20), nullable=False, server_default="any_authorized"),
        # State.
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("decided_by_email", sa.String(255), nullable=True),
        sa.Column("decided_by_user_id", sa.String(255), nullable=True),
        sa.Column("decided_reason", sa.Text, nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("timeout_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'timed_out')",
            name="ck_guard_approval_status",
        ),
        sa.CheckConstraint(
            "approval_type IN ('peer', 'any_admin', 'any_security', 'any_authorized')",
            name="ck_guard_approval_type",
        ),
    )
    op.create_index(
        "idx_guard_approvals_ws_status",
        "guard_approval_requests",
        ["workspace_id", "status", "created_at"],
    )
    op.create_index(
        "idx_guard_approvals_ws_requester",
        "guard_approval_requests",
        ["workspace_id", "requester_email"],
    )
    op.create_index(
        "idx_guard_approvals_source_run",
        "guard_approval_requests",
        ["source_run_id"],
        postgresql_where=sa.text("source_run_id IS NOT NULL"),
    )
    # Partial index over pending rows only — used by the lazy timeout sweep.
    op.create_index(
        "idx_guard_approvals_pending_timeout",
        "guard_approval_requests",
        ["timeout_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # New permission for HITL decide action. Admin already gets everything via
    # the baseline "admin — all permissions" SELECT; grant explicitly to security.
    op.execute("""
        INSERT INTO permissions (name, description) VALUES
        ('platform.approvals.decide', 'Approve or reject pending Guard approval requests')
        ON CONFLICT (name) DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND r.workspace_id IS NULL
          AND p.name = 'platform.approvals.decide'
        ON CONFLICT DO NOTHING
    """)
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'security' AND r.workspace_id IS NULL
          AND p.name = 'platform.approvals.decide'
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM role_permissions
        WHERE permission_id IN (
            SELECT id FROM permissions WHERE name = 'platform.approvals.decide'
        )
    """)
    op.execute("DELETE FROM permissions WHERE name = 'platform.approvals.decide'")
    op.drop_index("idx_guard_approvals_pending_timeout", table_name="guard_approval_requests")
    op.drop_index("idx_guard_approvals_source_run", table_name="guard_approval_requests")
    op.drop_index("idx_guard_approvals_ws_requester", table_name="guard_approval_requests")
    op.drop_index("idx_guard_approvals_ws_status", table_name="guard_approval_requests")
    op.drop_table("guard_approval_requests")
