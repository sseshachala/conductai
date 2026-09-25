"""R13 completion — populate ``budget_reservations.deleted_agent_identity_id``
via a Postgres BEFORE DELETE trigger on ``agent_identities``.

Migration 0143 added the tombstone column but left population to "a
future trigger or app-level cleanup." App-level cleanup would need
every delete path (API endpoint, admin script, future migration) to
remember to run the copy first — a single trigger is one place, always
correct.

The trigger fires BEFORE the SET NULL FK cascade runs, so it can still
read the agent id off ``budget_reservations`` rows that point at the
about-to-be-deleted identity.
"""
from alembic import op


revision = "0152"
down_revision = "0151"
branch_labels = None
depends_on = None


_UP_TRIGGER = """
CREATE OR REPLACE FUNCTION _tombstone_agent_reservations()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE budget_reservations
       SET deleted_agent_identity_id = OLD.id
     WHERE agent_identity_id = OLD.id
       AND deleted_agent_identity_id IS NULL;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_tombstone_agent_reservations ON agent_identities;
CREATE TRIGGER trg_tombstone_agent_reservations
    BEFORE DELETE ON agent_identities
    FOR EACH ROW
    EXECUTE FUNCTION _tombstone_agent_reservations();
"""


_DOWN_TRIGGER = """
DROP TRIGGER IF EXISTS trg_tombstone_agent_reservations ON agent_identities;
DROP FUNCTION IF EXISTS _tombstone_agent_reservations();
"""


def upgrade() -> None:
    op.execute(_UP_TRIGGER)


def downgrade() -> None:
    op.execute(_DOWN_TRIGGER)
