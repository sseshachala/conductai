"""Add two-phase lifecycle columns to guard_audit_events.

Phase 1 of #1959 — the accepted-then-finalized pattern. Every column is
nullable initially so historical rows and Phase-0 single-phase writers
keep working; Phase 2+ will migrate callers to the new writers behind
the ``guard_use_durable_audit`` feature flag.

Columns:
  - request_id        UUID           correlates the accepted and finalized
                                     writes for one HTTP request. Nullable
                                     for historical rows; a partial unique
                                     index enforces one-row-per-request-id
                                     only where the column is populated.
  - lifecycle_state   VARCHAR(20)    'accepted' | 'finalized' | 'orphaned'
                                     | 'expired'. NULL for pre-durable
                                     rows so Phase-0 writers stay valid.
  - accepted_at       TIMESTAMPTZ    pre-inference timestamp
  - finalized_at      TIMESTAMPTZ    post-inference timestamp
  - lease_expires_at  TIMESTAMPTZ    when the reconciler (Phase 4) can
                                     flip a still-'accepted' row to
                                     'orphaned'. Partial index on the
                                     'accepted' subset makes that scan
                                     O(orphans), not O(all).

Indexes named explicitly per the schema-drift regression test.

Revision ID: 0132
Revises: 0131
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0132"
down_revision = "0131"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_audit_events",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("lifecycle_state", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "guard_audit_events",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Correlate the accepted + finalized writes: one row per request_id.
    op.create_index(
        "ux_guard_audit_events_request_id",
        "guard_audit_events",
        ["request_id"],
        unique=True,
        postgresql_where=sa.text("request_id IS NOT NULL"),
    )

    # Reconciler (Phase 4) scans only 'accepted' rows whose lease has
    # expired. Partial index keeps the scan cheap once the durable
    # writer is on for real traffic.
    op.create_index(
        "ix_guard_audit_events_accepted_lease",
        "guard_audit_events",
        ["workspace_id", "lease_expires_at"],
        postgresql_where=sa.text("lifecycle_state = 'accepted'"),
    )


def downgrade():
    op.drop_index(
        "ix_guard_audit_events_accepted_lease", table_name="guard_audit_events"
    )
    op.drop_index(
        "ux_guard_audit_events_request_id", table_name="guard_audit_events"
    )
    op.drop_column("guard_audit_events", "lease_expires_at")
    op.drop_column("guard_audit_events", "finalized_at")
    op.drop_column("guard_audit_events", "accepted_at")
    op.drop_column("guard_audit_events", "lifecycle_state")
    op.drop_column("guard_audit_events", "request_id")
