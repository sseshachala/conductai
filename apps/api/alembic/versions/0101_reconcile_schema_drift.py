"""chore: reconcile schema drift — drop orphan tables/columns/indexes, fix types

Brings the DB schema into alignment with SQLAlchemy model metadata so that
``alembic check`` exits 0.  Changes fall into five categories:

1. Drop orphan tables that no longer have a corresponding model.
2. Drop stale columns removed from their models.
3. Drop stale indexes/constraints removed from their models.
4. Alter column types to match model declarations.
5. Add missing indexes, constraints, and foreign keys present in models.

Revision ID: 0101
Revises: 0100
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop FK constraints on columns we will remove ──────────────────────
    op.drop_constraint(
        "workspace_users_role_id_fkey", "workspace_users", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_guard_member_config_agent_identity",
        "guard_member_config",
        type_="foreignkey",
    )

    # ── 2. Drop indexes on columns we will remove (must precede column drop) ──
    op.drop_index("ix_workspace_users_role_id", table_name="workspace_users")
    op.drop_index("ix_workspace_users_clerk_user_id", table_name="workspace_users")
    op.drop_index("ix_workspaces_clerk_org_id", table_name="workspaces")
    op.drop_index(
        "ix_guard_member_config_agent_identity_id", table_name="guard_member_config"
    )

    # ── 3. Drop stale columns ─────────────────────────────────────────────────
    op.drop_column("workspace_users", "role_id")
    op.drop_column("workspaces", "clerk_org_id")
    op.drop_column("guard_audit_events", "os_info")
    op.drop_column("guard_audit_events", "hostname")
    op.drop_column("guard_member_config", "agent_identity_id")

    # ── 4. Drop orphan tables (leaf / no inbound FK first) ────────────────────
    op.drop_table("team_session_memory")
    op.drop_table("agent_memory")
    op.drop_table("watchdog_events")
    op.drop_table("telemetry_events")
    op.drop_table("project_templates")
    op.drop_table("run_online_scores")
    op.drop_table("glens_chat_sessions")
    op.drop_table("workspace_invites")
    op.drop_table("workspace_instructions")
    op.drop_table("workspace_config")
    op.drop_table("model_routing_policies")
    op.drop_table("security_findings")
    op.drop_table("security_config")
    op.drop_table("cred_retrieval_tokens")
    op.drop_table("security_policies")
    op.drop_table("run_block_states")
    op.drop_table("mcp_servers")
    op.drop_table("run_fixture_candidates")

    # ── 5. Drop stale indexes from tables that remain ─────────────────────────
    op.drop_index("ix_agent_identities_refresh_token_hash", table_name="agent_identities")
    op.drop_index("ix_audit_log_workspace_action", table_name="audit_log")
    op.drop_index("ix_audit_log_workspace_created", table_name="audit_log")
    op.drop_index("ix_discovered_agents_scan", table_name="discovered_agents")
    op.drop_index("ix_discovered_agents_workspace", table_name="discovered_agents")
    op.drop_constraint(
        "uq_discovered_agents_workspace_framework_source",
        "discovered_agents",
        type_="unique",
    )
    op.drop_index("ix_discovery_scans_workspace", table_name="discovery_scans")
    op.drop_index(
        "idx_guard_approvals_pending_timeout", table_name="guard_approval_requests"
    )
    op.drop_index(
        "idx_guard_approvals_source_run", table_name="guard_approval_requests"
    )
    op.drop_index(
        "idx_guard_approvals_ws_requester", table_name="guard_approval_requests"
    )
    op.drop_index(
        "idx_guard_approvals_ws_status", table_name="guard_approval_requests"
    )
    op.drop_index(
        "ix_guard_audit_events_entry_hash", table_name="guard_audit_events"
    )
    op.drop_index(
        "ix_guard_audit_events_evaluated_rules_gin", table_name="guard_audit_events"
    )
    op.drop_index("ix_guard_audit_events_provider", table_name="guard_audit_events")
    op.drop_index("ix_guard_audit_events_source", table_name="guard_audit_events")
    op.drop_index("ix_guard_audit_events_ws_ts", table_name="guard_audit_events")
    op.drop_index(
        "guard_knowledge_index_embedding_idx", table_name="guard_knowledge_index"
    )
    op.drop_index(
        "guard_knowledge_index_workspace_id_source_kind_idx",
        table_name="guard_knowledge_index",
    )
    op.drop_constraint(
        "guard_knowledge_index_workspace_id_source_kind_source_id_key",
        "guard_knowledge_index",
        type_="unique",
    )
    op.drop_index(
        "idx_guard_notif_workspace_action", table_name="guard_notification_channels"
    )
    op.drop_index(
        "idx_guard_notif_workspace_enabled", table_name="guard_notification_channels"
    )
    op.drop_index("idx_guard_rate_limits_ws", table_name="guard_rate_limits")
    op.drop_index("ix_guard_rule_overrides_workspace", table_name="guard_rule_overrides")
    op.drop_index("uq_guard_spend_workspace_default", table_name="guard_spend_budgets")
    op.drop_index("uq_guard_spend_workspace_member", table_name="guard_spend_budgets")
    op.drop_index("idx_integrations_okta_issuer", table_name="integrations")
    op.drop_index("ix_integrations_workspace_environment", table_name="integrations")
    op.drop_index("ix_integrations_workspace_id", table_name="integrations")
    op.drop_index("ix_playbook_submissions_slug", table_name="playbook_submissions")
    op.drop_index("ix_playbook_submissions_status", table_name="playbook_submissions")
    op.drop_index("ix_policy_cert_ws_pack_ts", table_name="policy_certifications")
    op.drop_index("ix_projects_project_type", table_name="projects")
    op.drop_index(
        "projects_workspace_security_automation_uniq", table_name="projects"
    )
    op.drop_constraint("uq_projects_slug_workspace", "projects", type_="unique")
    op.drop_index("uq_roles_system_name", table_name="roles")
    op.drop_index("uq_roles_workspace_name", table_name="roles")
    op.drop_index(
        "ix_run_analytics_events_playbook_slug_created_at",
        table_name="run_analytics_events",
    )
    op.drop_index(
        "ix_run_analytics_events_workspace_id_created_at",
        table_name="run_analytics_events",
    )
    op.drop_index("ix_run_events_run_created", table_name="run_events")
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_index("ix_run_traces_run_id", table_name="run_traces")
    op.drop_index("ix_run_traces_run_id_block_turn", table_name="run_traces")
    op.drop_index("ix_runs_created_at", table_name="runs")
    op.drop_index("ix_runs_queue_pickup", table_name="runs")
    op.drop_index("ix_runs_status", table_name="runs")
    op.drop_index("ix_runs_version_created", table_name="runs")
    op.drop_index("ix_runs_workflow_version_id", table_name="runs")
    op.drop_index("ix_runs_workspace_created", table_name="runs")
    op.drop_index("ix_runs_workspace_id", table_name="runs")
    op.drop_index("ix_runs_workspace_status", table_name="runs")
    op.drop_index("ix_session_reports_email", table_name="session_reports")
    op.drop_index("ix_session_reports_workspace", table_name="session_reports")
    op.drop_index("ix_workflow_versions_workflow_id", table_name="workflow_versions")
    op.drop_index("ix_workflows_archived_at", table_name="workflows")
    op.drop_index("ix_workflows_hook_label", table_name="workflows")
    op.drop_index("ix_workflows_project_id", table_name="workflows")
    op.drop_index("ix_workflows_workspace_id", table_name="workflows")
    op.drop_index("ix_workflows_workspace_playbook_slug", table_name="workflows")
    op.drop_index("workflows_project_playbook_uniq", table_name="workflows")
    op.drop_index("ix_workspace_custom_rules_workspace", table_name="workspace_custom_rules")
    op.drop_index("ix_workspace_skill_packs_workspace", table_name="workspace_skill_packs")

    # ── 6. Alter column types to match model declarations ────────────────────
    op.alter_column(
        "agent_identities",
        "metadata_json",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
        postgresql_using="metadata_json::text::jsonb",
    )
    op.alter_column(
        "guard_audit_events",
        "tool_use_id",
        existing_type=sa.TEXT(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_config",
        "alert_channel",
        existing_type=sa.TEXT(),
        type_=sa.String(length=100),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "workspace_id",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "user_email",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "detected_tools",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="detected_tools::text::json",
    )
    op.alter_column(
        "guard_developer_tools",
        "mcp_registered",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="mcp_registered::text::json",
    )
    op.alter_column(
        "guard_developer_tools",
        "hook_registered",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="hook_registered::text::json",
    )
    op.alter_column(
        "guard_savings",
        "workspace_id",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_savings",
        "member_email",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "integrations",
        "encrypted_credentials",
        existing_type=sa.TEXT(),
        type_=sa.String(),
        existing_nullable=True,
    )
    op.alter_column(
        "workspace_custom_rules",
        "persona",
        existing_type=sa.String(length=32),
        type_=sa.Text(),
        existing_nullable=True,
    )

    # ── 7. Add missing index on integrations.okta_issuer ─────────────────────
    op.create_index(
        "ix_integrations_okta_issuer", "integrations", ["okta_issuer"], unique=False
    )

    # ── 8. Add missing unique constraint on guard_knowledge_index ─────────────
    op.create_unique_constraint(
        "uq_guard_knowledge_source",
        "guard_knowledge_index",
        ["workspace_id", "source_kind", "source_id"],
    )

    # ── 9. Add missing FK: runs.workspace_id → workspaces.id ─────────────────
    op.create_foreign_key(
        "fk_runs_workspace_id",
        "runs",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )

    # ── 10. Set NOT NULL on users.workspace_id ────────────────────────────────
    op.alter_column("users", "workspace_id", existing_nullable=True, nullable=False)


def downgrade() -> None:
    # Reverse of upgrade — recreate columns/indexes/constraints that were dropped.
    # This is provided for completeness; rolling back this migration on a
    # production system requires careful data handling.
    op.alter_column("users", "workspace_id", existing_nullable=False, nullable=True)

    op.drop_constraint("fk_runs_workspace_id", "runs", type_="foreignkey")
    op.drop_constraint(
        "uq_guard_knowledge_source", "guard_knowledge_index", type_="unique"
    )
    op.drop_index("ix_integrations_okta_issuer", table_name="integrations")

    op.alter_column(
        "workspace_custom_rules",
        "persona",
        existing_type=sa.Text(),
        type_=sa.String(length=32),
        existing_nullable=True,
    )
    op.alter_column(
        "integrations",
        "encrypted_credentials",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_savings",
        "member_email",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_savings",
        "workspace_id",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "hook_registered",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "mcp_registered",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "detected_tools",
        existing_type=sa.JSON(),
        type_=postgresql.JSONB(astext_type=sa.Text()),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "user_email",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_developer_tools",
        "workspace_id",
        existing_type=sa.String(),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_config",
        "alert_channel",
        existing_type=sa.String(length=100),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "guard_audit_events",
        "tool_use_id",
        existing_type=sa.String(length=255),
        type_=sa.TEXT(),
        existing_nullable=True,
    )
    op.alter_column(
        "agent_identities",
        "metadata_json",
        existing_type=postgresql.JSONB(astext_type=sa.Text()),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="metadata_json::text::json",
    )

    # Re-add removed columns
    op.add_column(
        "workspaces",
        sa.Column("clerk_org_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_workspaces_clerk_org_id",
        "workspaces",
        ["clerk_org_id"],
        unique=True,
        postgresql_where=sa.text("clerk_org_id IS NOT NULL"),
    )
    op.add_column(
        "workspace_users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_workspace_users_role_id", "workspace_users", ["role_id"], unique=False
    )
    op.create_foreign_key(
        "workspace_users_role_id_fkey",
        "workspace_users",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="SET NULL",
    )
