"""Promote profile-specific agent caps to agent-wide Gateway caps."""
from alembic import op
import sqlalchemy as sa

revision = "0164"
down_revision = "0163"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    bind = op.get_bind()
    # RLS applies to migration owners too. Preserve legacy rows for rollback;
    # the new runtime reads only shared caps from this table.
    for workspace in bind.execute(sa.text("SELECT id FROM workspaces")).scalars():
        bind.execute(sa.text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(workspace)})
        bind.execute(sa.text("""
            INSERT INTO guard_rate_limits (id, workspace_id, agent_identity_id, rpm, tpm, created_at, updated_at)
            SELECT gen_random_uuid(), workspace_id, agent_identity_id, min(rpm), min(tpm), now(), now()
            FROM gateway_profile_rate_limits
            WHERE workspace_id = :ws AND agent_identity_id IS NOT NULL
            GROUP BY workspace_id, agent_identity_id
            ON CONFLICT (workspace_id, agent_identity_id) DO UPDATE
            SET rpm = LEAST(guard_rate_limits.rpm, EXCLUDED.rpm),
                tpm = LEAST(guard_rate_limits.tpm, EXCLUDED.tpm), updated_at = now()
        """), {"ws": workspace})


def downgrade():
    # Agent-wide configuration remains in the pre-existing table. Legacy
    # profile-agent rows were retained and become authoritative again in 0163.
    pass
