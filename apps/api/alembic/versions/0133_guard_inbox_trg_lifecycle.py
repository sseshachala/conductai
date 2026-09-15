"""Fire guard_inbox_populate on UPDATE OF decision too.

Phase 2 of #1959. The Phase 1 durable writer emits an 'accepted' row
via INSERT (decision='accepted') and later UPDATEs it to a terminal
value ('blocked' | 'warned' | 'approved'). The existing AFTER INSERT
trigger only fires on the INSERT — and correctly skips 'accepted'
because it's not a terminal enforcement outcome. That means the UPDATE
that flips the row to 'blocked' never populates guard_inbox, so
block-worthy durable-path calls would silently miss triage.

Add a paired AFTER UPDATE OF decision trigger with a WHEN clause that
fires only when the decision actually changes to a terminal enforcement
value. The trigger function itself (guard_inbox_populate) is shared and
doesn't distinguish INSERT vs UPDATE — it inspects NEW.* the same way.

Idempotent: the target guard_inbox row uses ON CONFLICT (workspace_id,
dedup_key) DO UPDATE so a subsequent identical fire increments the
occurrences counter rather than creating a duplicate.

Revision ID: 0133
Revises: 0132
"""
from alembic import op


revision = "0133"
down_revision = "0132"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TRIGGER guard_inbox_populate_upd_trg
        AFTER UPDATE OF decision ON guard_audit_events
        FOR EACH ROW
        WHEN (
            NEW.decision IS DISTINCT FROM OLD.decision
            AND NEW.decision IN ('blocked', 'warned', 'approved')
        )
        EXECUTE FUNCTION guard_inbox_populate();
    """)


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS guard_inbox_populate_upd_trg ON guard_audit_events;")
