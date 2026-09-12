"""Drop the code-scan module schema, add guard_inbox + trigger + backfill.

Revision ID: 0123
Revises: 0122
Create Date: 2026-09-12

Part of #1840 pivot. The /secure surface was removed in PR #1846 (code
side); this migration lands the schema half:

Drops:
  - security_findings table (no writer left after #1846)
  - security_config table (config for the removed auto-fix flow)
  - workspaces.security_automation_project_id column
  - projects.security_finding_id column
  - Partial unique index projects_workspace_security_automation_uniq

Creates:
  - guard_inbox table — dedup'd triage inbox for guard_audit_events
  - guard_inbox_populate() plpgsql function
  - AFTER INSERT trigger on guard_audit_events that upserts into
    guard_inbox with dedup + auto-reopen semantics

Backfills:
  - Last 30 days of blocked/warned/approved rows from guard_audit_events
    into guard_inbox via the same UPSERT logic the trigger uses
    (idempotent via ON CONFLICT).

Downgrade recreates empty structures; data is not restored (the drop
side lost the original rows). Kept for schema-symmetry only.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers
revision = "0123"
down_revision = "0122"
branch_labels = None
depends_on = None


# ── Guard inbox trigger function body ─────────────────────────────────────
# Kept as a module constant so the same string is reused in upgrade() and
# in test fixtures (guard_inbox_populate is the source of truth for the
# dedup + auto-reopen behavior).
GUARD_INBOX_POPULATE_FN = """
CREATE OR REPLACE FUNCTION guard_inbox_populate() RETURNS TRIGGER AS $body$
DECLARE
    v_dedup TEXT;
    v_severity TEXT;
BEGIN
    -- Only enforcement outcomes surface in the inbox. Plain 'allowed'
    -- rows stay in guard_audit_events (the raw firehose) and never
    -- create a finding.
    IF NEW.decision NOT IN ('blocked', 'warned', 'approved') THEN
        RETURN NEW;
    END IF;

    -- A rule_id is required to compute a stable dedup key. Rows without
    -- one (should be rare — pre-#1750 events perhaps) are skipped so
    -- they don't collapse into a garbage bucket.
    IF NEW.rule_id IS NULL THEN
        RETURN NEW;
    END IF;

    v_dedup := encode(
        digest(
            NEW.workspace_id::text ||
            COALESCE(NEW.rule_id, '') ||
            COALESCE(NEW.source, '') ||
            LEFT(COALESCE(NEW.rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    );

    v_severity := CASE NEW.decision
        WHEN 'blocked'  THEN 'critical'
        WHEN 'warned'   THEN 'medium'
        WHEN 'approved' THEN 'low'
    END;

    INSERT INTO guard_inbox (
        workspace_id, dedup_key, rule_id, source, severity,
        description, latest_event_id, first_seen_at, last_seen_at
    )
    VALUES (
        NEW.workspace_id, v_dedup, NEW.rule_id, NEW.source, v_severity,
        NEW.rule_message, NEW.id, NEW.ts, NEW.ts
    )
    ON CONFLICT (workspace_id, dedup_key) DO UPDATE
    SET occurrences     = guard_inbox.occurrences + 1,
        last_seen_at    = NEW.ts,
        latest_event_id = NEW.id,
        -- Auto-reopen: if a resolved finding fires again, flip status
        -- back to open and clear the resolution metadata so triage
        -- surfaces the pattern for review.
        status          = CASE WHEN guard_inbox.status = 'resolved'
                               THEN 'open' ELSE guard_inbox.status END,
        resolved_reason = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_reason END,
        resolved_at     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_at END,
        resolved_by     = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_by END,
        resolved_note   = CASE WHEN guard_inbox.status = 'resolved'
                               THEN NULL ELSE guard_inbox.resolved_note END;

    RETURN NEW;
END;
$body$ LANGUAGE plpgsql;
"""


# 30-day backfill uses the same dedup/severity logic as the trigger.
# Kept in sync manually — if the trigger changes, this must change too.
GUARD_INBOX_BACKFILL_30D = """
INSERT INTO guard_inbox (
    workspace_id, dedup_key, rule_id, source, severity,
    description, latest_event_id, first_seen_at, last_seen_at, occurrences
)
SELECT
    workspace_id,
    encode(
        digest(
            workspace_id::text ||
            COALESCE(rule_id, '') ||
            COALESCE(source, '') ||
            LEFT(COALESCE(rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    ) AS dedup_key,
    -- First occurrence's rule_id / source / description win for the
    -- initial row; subsequent rows update via ON CONFLICT.
    (array_agg(rule_id ORDER BY ts ASC))[1],
    (array_agg(source  ORDER BY ts ASC))[1],
    (array_agg(CASE decision
        WHEN 'blocked'  THEN 'critical'
        WHEN 'warned'   THEN 'medium'
        WHEN 'approved' THEN 'low'
     END ORDER BY ts ASC))[1],
    (array_agg(rule_message ORDER BY ts ASC))[1],
    (array_agg(id ORDER BY ts DESC))[1] AS latest_event_id,
    MIN(ts) AS first_seen_at,
    MAX(ts) AS last_seen_at,
    COUNT(*) AS occurrences
FROM guard_audit_events
WHERE decision IN ('blocked', 'warned', 'approved')
  AND rule_id IS NOT NULL
  AND ts > NOW() - INTERVAL '30 days'
GROUP BY
    workspace_id,
    encode(
        digest(
            workspace_id::text ||
            COALESCE(rule_id, '') ||
            COALESCE(source, '') ||
            LEFT(COALESCE(rule_message, ''), 200),
            'sha256'
        ),
        'hex'
    )
ON CONFLICT (workspace_id, dedup_key) DO NOTHING;
"""


def upgrade() -> None:
    # pgcrypto provides digest() used by the trigger + backfill. Idempotent
    # if already present (it is, since gen_random_uuid() is used elsewhere).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # ── Drop the removed code-scan surface ──────────────────────────────
    # Non-CONCURRENTLY drop: alembic runs inside a transaction, and
    # CONCURRENTLY is disallowed there. The lock window is negligible
    # because the index is on the projects table which nothing writes
    # while this migration runs.
    op.execute(
        "DROP INDEX IF EXISTS projects_workspace_security_automation_uniq"
    )

    # Use raw DDL with IF EXISTS so the up/down cycle CI test survives.
    # The downgrade is best-effort and doesn't recreate security_config /
    # security_findings tables (data is gone by design). Without IF EXISTS
    # a downgrade-then-upgrade would fail here on the second upgrade pass.
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS security_finding_id")
    op.execute(
        "ALTER TABLE workspaces "
        "DROP COLUMN IF EXISTS security_automation_project_id"
    )

    # Dependent tables first — security_config had a workspace_id FK
    # with ON DELETE CASCADE but no other table depends on it.
    op.execute("DROP TABLE IF EXISTS security_config")
    op.execute("DROP TABLE IF EXISTS security_findings")

    # ── Create guard_inbox ──────────────────────────────────────────────
    op.create_table(
        "guard_inbox",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("rule_id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        # severity is derived at trigger time from decision; kept as
        # denormalized text so the UI can render/filter without a JOIN.
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "occurrences",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Lifecycle: open → triaging → resolved. Auto-reopen on re-fire.
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default="open",
        ),
        # Enum enforced at the router layer (Pydantic): expected /
        # escalated / exception_added / false_positive.
        sa.Column("resolved_reason", sa.Text(), nullable=True),
        sa.Column("resolved_note", sa.Text(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.Text(), nullable=True),
        # Denormalized pointer to the most recent audit event so the
        # detail view can link straight to it without a range scan.
        sa.Column("latest_event_id", UUID(as_uuid=True), nullable=True),
        sa.UniqueConstraint(
            "workspace_id",
            "dedup_key",
            name="guard_inbox_workspace_dedup_uniq",
        ),
    )

    # Named indexes — CLAUDE.md rule: every Index/UniqueConstraint/ForeignKey
    # gets an explicit name= so drift diffs stay clean.
    op.create_index(
        "guard_inbox_ws_status_last_seen_idx",
        "guard_inbox",
        ["workspace_id", "status", sa.text("last_seen_at DESC")],
    )
    op.create_index(
        "guard_inbox_ws_severity_last_seen_idx",
        "guard_inbox",
        ["workspace_id", "severity", sa.text("last_seen_at DESC")],
    )

    # ── Trigger function + attachment ───────────────────────────────────
    op.execute(GUARD_INBOX_POPULATE_FN)
    op.execute(
        "DROP TRIGGER IF EXISTS guard_inbox_populate_trg "
        "ON guard_audit_events"
    )
    op.execute(
        "CREATE TRIGGER guard_inbox_populate_trg "
        "AFTER INSERT ON guard_audit_events "
        "FOR EACH ROW EXECUTE FUNCTION guard_inbox_populate()"
    )

    # ── 30-day backfill ─────────────────────────────────────────────────
    op.execute(GUARD_INBOX_BACKFILL_30D)


def downgrade() -> None:
    # Reverses the CREATE side only. The DROP side is not restored —
    # security-findings/security_config data is gone by design. Kept
    # for schema symmetry so alembic downgrade doesn't error mid-flight.
    op.execute(
        "DROP TRIGGER IF EXISTS guard_inbox_populate_trg "
        "ON guard_audit_events"
    )
    op.execute("DROP FUNCTION IF EXISTS guard_inbox_populate()")
    op.drop_index(
        "guard_inbox_ws_severity_last_seen_idx", table_name="guard_inbox"
    )
    op.drop_index(
        "guard_inbox_ws_status_last_seen_idx", table_name="guard_inbox"
    )
    op.drop_table("guard_inbox")

    # Recreate the dropped tables/columns empty. Data is not restored.
    op.add_column(
        "workspaces",
        sa.Column(
            "security_automation_project_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "projects",
        sa.Column(
            "security_finding_id",
            sa.String(length=36),
            nullable=True,
        ),
    )
    op.create_index(
        op.f("ix_projects_security_finding_id"),
        "projects",
        ["security_finding_id"],
        unique=False,
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS "
        "projects_workspace_security_automation_uniq "
        "ON projects (workspace_id) "
        "WHERE project_type = 'security_automation'"
    )

    # security_findings + security_config tables are NOT recreated —
    # downgrade is best-effort; the schema shape can be restored from an
    # earlier revision (e.g. 0087) if a full rollback is needed. This
    # migration's job is forward-only in practice.
