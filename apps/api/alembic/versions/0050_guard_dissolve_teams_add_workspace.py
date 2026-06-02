"""Guard: create guard_config + guard_member_config, add workspace_id/clerk_user_id to child tables

Creates the two new workspace-keyed tables and backfills from existing guard_teams/guard_members.
Adds workspace_id (nullable) and clerk_user_id (nullable) to child tables, then backfills.

Revision ID: 0050
Revises: 0049
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. guard_config ────────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_config (
            workspace_id   UUID PRIMARY KEY REFERENCES workspaces(id) ON DELETE CASCADE,
            invite_code    TEXT NOT NULL DEFAULT encode(gen_random_bytes(16), 'hex'),
            slug           TEXT,
            alert_channel  TEXT,
            notify_on_block  BOOLEAN NOT NULL DEFAULT true,
            notify_on_budget BOOLEAN NOT NULL DEFAULT true,
            created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at     TIMESTAMPTZ
        )
    """)

    # Backfill from guard_teams where workspace_id IS NOT NULL
    op.execute("""
        INSERT INTO guard_config (workspace_id, invite_code, slug, alert_channel,
                                  notify_on_block, notify_on_budget, created_at, updated_at)
        SELECT workspace_id,
               invite_code,
               slug,
               alert_channel,
               notify_on_block,
               notify_on_budget,
               created_at,
               updated_at
        FROM guard_teams
        WHERE workspace_id IS NOT NULL
        ON CONFLICT (workspace_id) DO NOTHING
    """)

    # ── 2. guard_member_config ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_member_config (
            workspace_id   UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            clerk_user_id  TEXT NOT NULL,
            member_token   TEXT NOT NULL DEFAULT encode(gen_random_bytes(32), 'hex'),
            active         BOOLEAN NOT NULL DEFAULT true,
            joined_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (workspace_id, clerk_user_id)
        )
    """)

    # Backfill from guard_members JOIN guard_teams where workspace_id is set
    # guard_members.user_id maps to clerk_user_id; skip rows with NULL user_id
    op.execute("""
        INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
        SELECT gt.workspace_id,
               gm.user_id,
               COALESCE(gm.member_token, encode(gen_random_bytes(32), 'hex')),
               gm.active,
               COALESCE(gm.joined_at, now())
        FROM guard_members gm
        JOIN guard_teams gt ON gt.id = gm.team_id
        WHERE gt.workspace_id IS NOT NULL
          AND gm.user_id IS NOT NULL
        ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
    """)

    # ── 3. Add workspace_id to child tables ────────────────────────────────────
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS workspace_id UUID
            REFERENCES workspaces(id) ON DELETE CASCADE
        """)

    # ── 4. Add clerk_user_id to tables that had member_id ──────────────────────
    for table in ("guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            ALTER TABLE {table}
            ADD COLUMN IF NOT EXISTS clerk_user_id TEXT
        """)

    # ── 5. Backfill workspace_id on all four tables via JOIN guard_teams ────────
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            UPDATE {table} t
            SET workspace_id = gt.workspace_id
            FROM guard_teams gt
            WHERE gt.id = t.team_id
              AND gt.workspace_id IS NOT NULL
              AND t.workspace_id IS NULL
        """)

    # ── 6. Backfill clerk_user_id via JOIN guard_members on member_id ───────────
    for table in ("guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"""
            UPDATE {table} t
            SET clerk_user_id = gm.user_id
            FROM guard_members gm
            WHERE gm.id = t.member_id
              AND gm.user_id IS NOT NULL
              AND t.clerk_user_id IS NULL
        """)


def downgrade() -> None:
    for table in ("guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS clerk_user_id")
    for table in ("guard_policies", "guard_spend_budgets", "guard_audit_events", "guard_sessions"):
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS workspace_id")
    op.execute("DROP TABLE IF EXISTS guard_member_config")
    op.execute("DROP TABLE IF EXISTS guard_config")
