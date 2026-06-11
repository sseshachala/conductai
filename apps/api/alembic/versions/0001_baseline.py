"""Baseline — squashed from migrations 0001-0081.

IMPORTANT: existing databases that have already run migrations 0001-0081
must stamp themselves at this revision without re-running DDL:

    cd apps/api
    alembic stamp 0001

New databases: alembic upgrade head  (runs this migration only, creates full schema)

Extensions required on the Postgres instance:
  - pgcrypto   (gen_random_uuid)
  - vector     (pgvector — agent_memory and team_session_memory embeddings)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Extensions ──────────────────────────────────────────────────────────────
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')
    op.execute('CREATE EXTENSION IF NOT EXISTS "vector"')

    # =========================================================================
    # Tier 0 — no foreign keys
    # =========================================================================

    op.create_table(
        "organizations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )

    op.create_table(
        "email_templates",
        sa.Column("slug", sa.String(100), primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("html_body", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("variables", sa.JSON, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "project_templates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("default_mode", sa.String(50), nullable=False, server_default="dag"),
        sa.Column("nodes", JSONB, nullable=False, server_default="[]"),
        sa.Column("edges", JSONB, nullable=False, server_default="[]"),
    )

    op.create_table(
        "permissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
    )

    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=True),
        sa.Column("actor_email", sa.String(255), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_workspace_created", "audit_log", ["workspace_id", "created_at"])
    op.create_index("ix_audit_log_workspace_action", "audit_log", ["workspace_id", "action"])

    op.create_table(
        "run_analytics_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(16), nullable=False),
        sa.Column("playbook_slug", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("blocks_executed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("human_verdict", sa.String(50), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_run_analytics_events_playbook_slug_created_at", "run_analytics_events", ["playbook_slug", "created_at"])
    op.create_index("ix_run_analytics_events_workspace_id_created_at", "run_analytics_events", ["workspace_id", "created_at"])

    op.create_table(
        "run_online_scores",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("mechanical_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("mechanical_max", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("judge_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judge_max", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("judge_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("run_status", sa.String(50), nullable=True),
        sa.Column("outcome_type", sa.String(255), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("anonymized_outcome", JSONB, nullable=True),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_run_online_scores_run_id", "run_online_scores", ["run_id"], unique=True)
    op.create_index("ix_run_online_scores_slug", "run_online_scores", ["slug"])
    op.create_index("ix_run_online_scores_grade", "run_online_scores", ["grade"])
    op.create_index("ix_run_online_scores_scored_at", "run_online_scores", ["scored_at"])

    op.create_table(
        "run_fixture_candidates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("anon_trigger_payload", JSONB, nullable=True),
        sa.Column("anon_state", JSONB, nullable=True),
        sa.Column("expected_outcome_type", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("promoted_pr_url", sa.Text(), nullable=True),
        sa.Column("promoted_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_run_fixture_candidates_run_id", "run_fixture_candidates", ["run_id"], unique=True)
    op.create_index("ix_run_fixture_candidates_slug", "run_fixture_candidates", ["slug"])
    op.create_index("ix_run_fixture_candidates_status", "run_fixture_candidates", ["status"])

    op.create_table(
        "playbook_submissions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(255), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="builtin"),
        sa.Column("structural_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grade", sa.String(5), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("criteria_json", sa.Text(), nullable=True),
        sa.Column("eval_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("yaml_content", sa.Text(), nullable=True),
        sa.Column("submitter_email", sa.String(255), nullable=True),
        sa.Column("submitter_workspace_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_playbook_submissions_slug", "playbook_submissions", ["slug"])
    op.create_index("ix_playbook_submissions_status", "playbook_submissions", ["status"])

    op.create_table(
        "watchdog_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.String(255), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False, server_default="warning"),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "event_type IN ('token_spike','cost_spike','long_session','repeated_failure',"
            "'policy_block','budget_alert','idle_session','unknown')",
            name="ck_watchdog_events_event_type",
        ),
        sa.CheckConstraint(
            "severity IN ('info','warning','critical')",
            name="ck_watchdog_events_severity",
        ),
    )
    op.create_index("ix_watchdog_events_workspace_id", "watchdog_events", ["workspace_id"])
    op.create_index("ix_watchdog_events_created_at", "watchdog_events", ["created_at"])

    op.create_table(
        "security_findings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("tool", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("file", sa.String(), nullable=True),
        sa.Column("line", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("suggested_fix", sa.Text(), nullable=True),
        sa.Column("repo_full_name", sa.String(), nullable=True),
        sa.Column("commit_sha", sa.String(), nullable=True),
        sa.Column("source_run_id", sa.String(), nullable=True),
        sa.Column("reporter_email", sa.String(255), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="open"),
        sa.Column("github_issue_url", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_security_findings_workspace_id", "security_findings", ["workspace_id"])
    op.create_index("ix_security_findings_repo_full_name", "security_findings", ["repo_full_name"])
    op.create_index("ix_security_findings_created_at", "security_findings", ["created_at"])
    op.create_index("ix_security_findings_status", "security_findings", ["workspace_id", "status"])

    op.create_table(
        "guard_savings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("member_email", sa.Text(), nullable=False),
        sa.Column("rtk_saved_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("rtk_savings_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("rtk_total_commands", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("booster_saved_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("booster_savings_pct", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("booster_total_reads", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_guard_savings_workspace_id", "guard_savings", ["workspace_id"])

    op.create_table(
        "guard_developer_tools",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("user_email", sa.Text(), nullable=False),
        sa.Column("detected_tools", JSONB, nullable=False, server_default="[]"),
        sa.Column("mcp_registered", JSONB, nullable=False, server_default="[]"),
        sa.Column("hook_registered", JSONB, nullable=False, server_default="[]"),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "user_email", name="uq_guard_dev_tools"),
    )
    op.create_index("ix_guard_developer_tools_workspace_id", "guard_developer_tools", ["workspace_id"])

    # =========================================================================
    # Tier 1 — workspaces (references organizations)
    # =========================================================================

    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.String(255), nullable=True),
        sa.Column("is_approved", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("kms_key_id", sa.String(255), nullable=True),
        sa.Column("preferences", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True),
    )

    # =========================================================================
    # Tier 2 — depends on workspaces
    # =========================================================================

    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Partial unique indexes for roles
    op.execute("CREATE UNIQUE INDEX uq_roles_system_name ON roles (name) WHERE workspace_id IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_roles_workspace_name ON roles (workspace_id, name) WHERE workspace_id IS NOT NULL")

    op.create_table(
        "role_permissions",
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("permission_id", UUID(as_uuid=True), sa.ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("clerk_id", sa.String(255), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="developer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_users_clerk_id", "users", ["clerk_id"])

    op.create_table(
        "workspace_users",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("clerk_user_id", sa.String(255), primary_key=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="developer"),
        sa.Column("invited_by", sa.String(255), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("role_id", UUID(as_uuid=True), sa.ForeignKey("roles.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint(
            "role IN ('admin', 'security', 'developer', 'viewer')",
            name="ck_workspace_users_role",
        ),
    )
    op.create_index("ix_workspace_users_clerk_user_id", "workspace_users", ["clerk_user_id"])
    op.create_index("ix_workspace_users_role_id", "workspace_users", ["role_id"])

    op.create_table(
        "workspace_invites",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("invited_email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="developer"),
        sa.Column("invited_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workspace_id", "invited_email", name="uq_workspace_invite_email"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_workspace_invites_status",
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'security', 'developer', 'viewer')",
            name="ck_workspace_invites_role",
        ),
    )
    op.create_index("ix_workspace_invites_email", "workspace_invites", ["invited_email"])

    op.create_table(
        "environments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("allowed_hosts", JSONB, nullable=True),
        sa.UniqueConstraint("workspace_id", "name", name="uq_environments_workspace_name"),
    )

    op.create_table(
        "projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=True),
        sa.Column("project_type", sa.String(32), nullable=False, server_default="user"),
        sa.Column("security_finding_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_projects_slug_workspace"),
    )
    op.create_index("ix_projects_project_type", "projects", ["project_type"])
    op.create_index("ix_projects_security_finding_id", "projects", ["security_finding_id"])

    op.create_table(
        "conduct_api_keys",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="developer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('admin', 'security', 'developer', 'viewer')",
            name="ck_conduct_api_keys_role",
        ),
    )
    op.create_index("ix_conduct_api_keys_workspace_id", "conduct_api_keys", ["workspace_id"])

    op.create_table(
        "guard_config",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("invite_code", sa.Text(), nullable=False, server_default=sa.text("encode(gen_random_bytes(16), 'hex')")),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("alert_channel", sa.Text(), nullable=True),
        sa.Column("notify_on_block", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notify_on_budget", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enforcement_mode", sa.String(20), nullable=False, server_default="warn"),
        sa.Column("resync_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_guardrails", JSONB, nullable=True),
        sa.Column("guardrail_snapshot", JSONB, nullable=True),
        sa.Column("slack_webhook_url", sa.String(), nullable=True),
        sa.Column("alert_slack_integration_id", UUID(as_uuid=True), nullable=True),
        sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True),
        sa.Column("automation_security_scan", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("automation_workflow_trigger", sa.Boolean(), nullable=False, server_default="false"),
    )

    op.create_table(
        "guard_member_config",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("clerk_user_id", sa.Text(), nullable=False, primary_key=True),
        sa.Column("member_token", sa.Text(), nullable=False, server_default=sa.text("encode(gen_random_bytes(32), 'hex')")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "security_config",
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("installed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("security_emit_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("security_slack_alerts_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("security_slack_channel", sa.String(100), nullable=True),
        sa.Column("slack_webhook_url", sa.String(500), nullable=True),
        sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True),
        sa.Column("autopilot_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("automation_workflow_on_finding", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("automation_finding_severity", sa.String(20), nullable=False, server_default="critical"),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "security_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("pattern", sa.String(500), nullable=True),
        sa.Column("finding_type", sa.String(50), nullable=False, server_default="other"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_security_policies_workspace", "security_policies", ["workspace_id"])

    # =========================================================================
    # Tier 3 — depends on workspaces + environments / projects
    # =========================================================================

    op.create_table(
        "integrations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("service", sa.String(100), nullable=False),
        sa.Column("auth_method", sa.String(50), nullable=False),
        sa.Column("handle", sa.String(100), nullable=False),
        sa.Column("scopes", ARRAY(sa.String), nullable=True),
        sa.Column("encrypted_credentials", sa.Text, nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("environment_id", UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=True),
        sa.UniqueConstraint("workspace_id", "handle", "environment_id", name="uq_integrations_workspace_handle_env"),
    )
    op.create_index("ix_integrations_workspace_id", "integrations", ["workspace_id"])
    op.create_index("ix_integrations_workspace_environment", "integrations", ["workspace_id", "environment_id"])

    # guard_policies — depends on workspaces
    op.create_table(
        "guard_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("match_tool", sa.String(255), nullable=True),
        sa.Column("match_pattern", sa.String(500), nullable=True),
        sa.Column("match_path_pattern", sa.String(500), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Unique index: one rule_id per workspace
    op.execute("CREATE UNIQUE INDEX uq_guard_policies_workspace_rule ON guard_policies (workspace_id, rule_id)")

    # guard_spend_budgets — depends on workspaces
    op.create_table(
        "guard_spend_budgets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("monthly_limit_usd", sa.Float(), nullable=False),
        sa.Column("alert_threshold_pct", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("hard_limit_usd", sa.Float(), nullable=True),
        sa.Column("default_per_developer_usd", sa.Float(), nullable=True),
        sa.Column("last_alert_pct_bucket", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Partial unique indexes: one team-default row, one per-member row
    op.execute("CREATE UNIQUE INDEX uq_guard_spend_workspace_default ON guard_spend_budgets (workspace_id) WHERE clerk_user_id IS NULL")
    op.execute("CREATE UNIQUE INDEX uq_guard_spend_workspace_member ON guard_spend_budgets (workspace_id, clerk_user_id) WHERE clerk_user_id IS NOT NULL")

    # =========================================================================
    # Tier 4 — workflow_versions and workflows (circular dependency resolved manually)
    # =========================================================================

    # workflow_versions created first without FK to workflows.id
    op.create_table(
        "workflow_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_id", UUID(as_uuid=True), nullable=False),  # FK added after workflows
        sa.Column("yaml_source", sa.Text, nullable=True),
        sa.Column("graph", JSONB, nullable=False, server_default="{}"),
        sa.Column("compiled_artifacts", JSONB, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"])

    op.create_table(
        "workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("current_version_id", UUID(as_uuid=True), sa.ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True),
        sa.Column("default_mode", sa.String(50), nullable=False, server_default="dag"),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_repo", sa.String(255), nullable=True),
        sa.Column("source_path", sa.String(512), nullable=True),
        sa.Column("environment_id", UUID(as_uuid=True), sa.ForeignKey("environments.id"), nullable=True),
        sa.Column("github_hook_id", sa.String(255), nullable=True),
        sa.Column("github_hook_repo", sa.String(255), nullable=True),
        sa.Column("github_hook_label", sa.String(255), nullable=True),
        sa.Column("playbook_slug", sa.String(100), nullable=True),
        sa.Column("default_max_turns", sa.Integer(), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("source", sa.String(32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_workflows_workspace_id", "workflows", ["workspace_id"])
    op.create_index("ix_workflows_project_id", "workflows", ["project_id"])
    op.create_index("ix_workflows_workspace_playbook_slug", "workflows", ["workspace_id", "playbook_slug"])
    op.create_index(
        "ix_workflows_hook_label",
        "workflows",
        ["github_hook_repo", "github_hook_label"],
        postgresql_where=sa.text("github_hook_label IS NOT NULL"),
    )

    # Now add the FK from workflow_versions back to workflows (with CASCADE)
    op.create_foreign_key(
        "fk_workflow_versions_workflow_id",
        "workflow_versions", "workflows",
        ["workflow_id"], ["id"],
        ondelete="CASCADE",
    )

    # =========================================================================
    # Tier 5 — runs (depends on workflow_versions)
    # =========================================================================

    op.create_table(
        "runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workflow_version_id", UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_block_id", sa.String(255), nullable=True),
        sa.Column("max_turns", sa.Integer(), nullable=True),
        sa.Column("state", JSONB, nullable=False, server_default="{}"),
        sa.Column("outcome", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(255), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat_time", sa.DateTime(timezone=True), nullable=True),
    )
    # FK with CASCADE (added in 0080)
    op.create_foreign_key(
        "runs_workflow_version_id_fkey",
        "runs", "workflow_versions",
        ["workflow_version_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_runs_workflow_version_id", "runs", ["workflow_version_id"])
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_index("ix_runs_created_at", "runs", ["created_at"])
    op.create_index("ix_runs_version_created", "runs", ["workflow_version_id", "created_at"])
    op.create_index(
        "ix_runs_queue_pickup",
        "runs",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )

    # =========================================================================
    # Tier 6 — depends on runs
    # =========================================================================

    op.create_table(
        "run_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", sa.String(255), nullable=True),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # FK with CASCADE (added in 0080)
    op.create_foreign_key(
        "run_events_run_id_fkey",
        "run_events", "runs",
        ["run_id"], ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"])
    op.create_index("ix_run_events_run_created", "run_events", ["run_id", "created_at"])

    op.create_table(
        "run_traces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("block_id", sa.String(255), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(255), nullable=True),
        sa.Column("tool_input", JSONB, nullable=True),
        sa.Column("tool_use_id", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_run_traces_run_id", "run_traces", ["run_id"])
    op.create_index("ix_run_traces_run_id_block_turn", "run_traces", ["run_id", "block_id", "turn"])

    # agent_memory — depends on workspaces and runs
    op.create_table(
        "agent_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("playbook_slug", sa.String(100), nullable=False),
        sa.Column("scope", sa.String(50), nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), sa.ForeignKey("runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    # Add pgvector column (native vector type from migration 0073)
    op.execute("ALTER TABLE agent_memory ADD COLUMN embedding vector(1536)")
    op.create_index("ix_agent_memory_lookup", "agent_memory", ["workspace_id", "playbook_slug", "scope", "key"])
    op.create_index("ix_agent_memory_created", "agent_memory", ["workspace_id", "playbook_slug", "scope", "key", "created_at"])
    # Composite filter index for non-null embeddings (from 0060/0073)
    op.execute("""
        CREATE INDEX ix_agent_memory_search
        ON agent_memory (workspace_id, playbook_slug, scope, key)
        WHERE embedding IS NOT NULL
    """)
    # HNSW ANN index (from 0073)
    op.execute("""
        CREATE INDEX ix_agent_memory_hnsw
        ON agent_memory USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # guard_sessions — depends on workspaces
    op.create_table(
        "guard_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("ai_tool", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_tokens_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens_after", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_cost_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("total_saved_usd", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("violations_count", sa.Integer(), nullable=False, server_default="0"),
    )

    # guard_audit_events — depends on workspaces + guard_sessions
    op.create_table(
        "guard_audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("guard_sessions.id"), nullable=True),
        sa.Column("user_email", sa.String(255), nullable=True),
        sa.Column("ai_tool", sa.String(50), nullable=False),
        sa.Column("tool_call", sa.String(50), nullable=False),
        sa.Column("input_summary", sa.Text, nullable=True),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=True),
        sa.Column("rule_message", sa.Text, nullable=True),
        sa.Column("tokens_before", sa.Integer(), nullable=True),
        sa.Column("tokens_after", sa.Integer(), nullable=True),
        sa.Column("tokens_saved", sa.Integer(), nullable=True),
        sa.Column("cost_usd_before", sa.Float(), nullable=True),
        sa.Column("cost_usd_after", sa.Float(), nullable=True),
        sa.Column("conductai_run_id", sa.String(255), nullable=True),
        sa.Column("conductai_workflow", sa.String(255), nullable=True),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("tool_use_id", sa.Text(), nullable=True),
        sa.Column("hook_session_id", sa.Text(), nullable=True),
        sa.Column("blast_radius", JSONB, nullable=True),
    )
    op.create_index("ix_guard_audit_events_tool_use_id", "guard_audit_events", ["tool_use_id"])
    op.create_index("ix_guard_audit_events_hook_session_id", "guard_audit_events", ["hook_session_id"])

    # session_reports — depends on workspaces
    op.create_table(
        "session_reports",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("developer_email", sa.String(255), nullable=False),
        sa.Column("archetype", sa.String(100), nullable=True),
        sa.Column("autonomy_score", sa.Float(), nullable=True),
        sa.Column("planning_ratio", sa.Float(), nullable=True),
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("commits", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lines_per_hour", sa.Float(), nullable=True),
        sa.Column("active_days", sa.Integer(), nullable=True),
        sa.Column("tools_json", JSONB, nullable=True),
        sa.Column("report_md", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_session_reports_workspace", "session_reports", ["workspace_id"])
    op.create_index("ix_session_reports_email", "session_reports", ["developer_email"])

    # team_session_memory — depends on workspaces
    op.create_table(
        "team_session_memory",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("developer_id", sa.Text(), nullable=True),  # Clerk user_id (text since 0076)
        sa.Column("developer_email", sa.Text(), nullable=True),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("tool", sa.String(50), nullable=False, server_default="claude_code"),
        sa.Column("repo_full_name", sa.Text(), nullable=True),
        sa.Column("topic_tags", ARRAY(sa.Text()), nullable=True),
        sa.Column("light_summary", sa.Text(), nullable=False),
        sa.Column("deep_summary", sa.Text(), nullable=True),
        sa.Column("files_touched", ARRAY(sa.Text()), nullable=True),
        sa.Column("decisions", JSONB, nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("visibility", sa.String(20), nullable=False, server_default="team"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.execute("ALTER TABLE team_session_memory ADD COLUMN embedding vector(1536)")
    op.create_index("ix_tsm_workspace_repo", "team_session_memory", ["workspace_id", "repo_full_name"])
    op.execute("""
        CREATE INDEX ix_tsm_hnsw
        ON team_session_memory USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding IS NOT NULL
    """)

    # =========================================================================
    # Seed data — system roles and permissions (from 0044)
    # =========================================================================

    op.execute("""
        INSERT INTO permissions (name, description) VALUES
        ('platform.workflows.view',     'View workflows'),
        ('platform.workflows.edit',     'Create / edit / delete workflows'),
        ('platform.workflows.run',      'Trigger workflow runs'),
        ('platform.runs.view',          'View workflow runs'),
        ('platform.marketplace.browse', 'Browse marketplace'),
        ('platform.marketplace.install','Install from marketplace'),
        ('platform.eval.view',          'View eval / observability'),
        ('platform.workspace.edit',     'Edit workspace name and plan'),
        ('platform.members.manage',     'Invite, remove, and change member roles'),
        ('platform.credentials.manage', 'View, add, and delete credentials / environments'),
        ('platform.audit_log.view',     'View audit log'),
        ('guard.activity.view_all',     'View all members activity dashboard and log'),
        ('guard.activity.view_own',     'View own activity only'),
        ('guard.activity.export',       'Export activity CSV'),
        ('guard.spend.view_all',        'View all members spend'),
        ('guard.spend.view_own',        'View own spend'),
        ('guard.spend.budgets.edit',    'Set spending budgets'),
        ('guard.policies.view',         'View guard policies'),
        ('guard.policies.edit',         'Toggle, add, and delete guard policies'),
        ('guard.settings.edit',         'Edit Slack channel and notification settings')
    """)

    op.execute("""
        INSERT INTO roles (name, description, is_system) VALUES
        ('admin',     'Workspace owner. Full access to everything.',                              true),
        ('security',  'Security persona. Full Guard write access. Platform read + credentials.',  true),
        ('developer', 'Builder. Creates and runs workflows. Guard read-only, own activity only.', true),
        ('viewer',    'Read-only observer. Cannot write anything.',                               true)
    """)

    # admin — all permissions
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND r.workspace_id IS NULL
    """)

    # security
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'security' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.runs.view','platform.marketplace.browse',
            'platform.eval.view','platform.credentials.manage','platform.audit_log.view',
            'guard.activity.view_all','guard.activity.view_own','guard.activity.export',
            'guard.spend.view_all','guard.spend.view_own',
            'guard.policies.view','guard.policies.edit'
          )
    """)

    # developer
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'developer' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.workflows.edit','platform.workflows.run',
            'platform.runs.view','platform.marketplace.browse','platform.marketplace.install',
            'platform.eval.view',
            'guard.activity.view_own','guard.spend.view_own','guard.policies.view'
          )
    """)

    # viewer
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'viewer' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.runs.view',
            'platform.marketplace.browse','platform.eval.view',
            'guard.activity.view_own','guard.policies.view'
          )
    """)

    # Seed the dev workspace (from 0001)
    op.execute(
        "INSERT INTO workspaces (id, name, plan, is_approved, owner_id) VALUES "
        "('00000000-0000-0000-0000-000000000001', 'dev-workspace', 'free', true, 'dev')"
    )


def downgrade() -> None:
    # Intentionally left empty — baseline cannot be downgraded.
    # To restore: drop the entire database and recreate.
    pass
