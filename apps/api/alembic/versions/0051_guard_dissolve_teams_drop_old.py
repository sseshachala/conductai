"""Guard: drop team_id/member_id from child tables, make workspace_id NOT NULL, drop old tables

Final cleanup after 0050 backfill:
- DROP team_id from all four child tables
- DROP member_id from spend_budgets, audit_events, sessions
- Make workspace_id NOT NULL on all four child tables
- DROP TABLE guard_members
- DROP TABLE guard_teams

Revision ID: 0051
Revises: 0050
"""
from alembic import op
import sqlalchemy as sa

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. Drop team_id FK + column from all four child tables ─────────────────
    # Find and drop any FK constraints on team_id first (names may vary)
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            DO $$
            DECLARE
                _c TEXT;
            BEGIN
                SELECT tc.constraint_name INTO _c
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = tc.constraint_name
                 AND kcu.table_name = tc.table_name
                WHERE tc.table_name = '{table}'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'team_id'
                LIMIT 1;
                IF _c IS NOT NULL THEN
                    EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT ' || quote_ident(_c);
                END IF;
            END;
            $$;
        """)
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS team_id")

    # ── 2. Drop member_id FK + column from three child tables ──────────────────
    for table in ("guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            DO $$
            DECLARE
                _c TEXT;
            BEGIN
                SELECT tc.constraint_name INTO _c
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON kcu.constraint_name = tc.constraint_name
                 AND kcu.table_name = tc.table_name
                WHERE tc.table_name = '{table}'
                  AND tc.constraint_type = 'FOREIGN KEY'
                  AND kcu.column_name = 'member_id'
                LIMIT 1;
                IF _c IS NOT NULL THEN
                    EXECUTE 'ALTER TABLE {table} DROP CONSTRAINT ' || quote_ident(_c);
                END IF;
            END;
            $$;
        """)
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS member_id")

    # ── 3. Make workspace_id NOT NULL on all four child tables ─────────────────
    # Rows with NULL workspace_id (no matching guard_teams.workspace_id) are
    # deleted — they belonged to unlinked teams and have no owner in the new schema.
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"DELETE FROM {table} WHERE workspace_id IS NULL")
        op.execute(f"ALTER TABLE {table} ALTER COLUMN workspace_id SET NOT NULL")

    # ── 4. Drop old tables ─────────────────────────────────────────────────────
    op.execute("DROP TABLE IF EXISTS guard_members CASCADE")
    op.execute("DROP TABLE IF EXISTS guard_teams CASCADE")


def downgrade() -> None:
    # Minimal — recreate the tables and columns (no data recovery)
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_teams (
            id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name           TEXT NOT NULL,
            slug           TEXT NOT NULL UNIQUE,
            invite_code    TEXT NOT NULL UNIQUE,
            conductai_org_id TEXT,
            workspace_id   UUID REFERENCES workspaces(id) ON DELETE SET NULL,
            alert_channel  TEXT,
            notify_on_block  BOOLEAN NOT NULL DEFAULT true,
            notify_on_budget BOOLEAN NOT NULL DEFAULT true,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_members (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            team_id      UUID REFERENCES guard_teams(id) NOT NULL,
            user_id      TEXT NOT NULL,
            email        TEXT NOT NULL,
            role         TEXT NOT NULL DEFAULT 'developer',
            active       BOOLEAN NOT NULL DEFAULT true,
            joined_at    TIMESTAMPTZ,
            member_token TEXT UNIQUE
        )
    """)
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"ALTER TABLE {table} ALTER COLUMN workspace_id DROP NOT NULL")
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS team_id UUID")
    for table in ("guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS member_id UUID")
