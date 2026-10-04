"""Verified raw audit payload archives and legal holds; no data cleanup."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB
from alembic import op

revision = "0166"
down_revision = "0165"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("SET LOCAL lock_timeout = '3s'")
    op.create_table(
        "guard_audit_archive_segments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ordinal", sa.BigInteger(), nullable=False),
        sa.Column("manifest", JSONB(), nullable=False),
        sa.Column("manifest_hash", sa.String(64), nullable=False),
        sa.Column("signature", sa.String(64), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "ordinal", name="uq_guard_archive_ordinal"),
        sa.UniqueConstraint("workspace_id", "manifest_hash", name="uq_guard_archive_manifest"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_guard_archive_id_workspace"),
        sa.CheckConstraint("ordinal > 0", name="ck_guard_archive_ordinal"),
    )
    op.create_table(
        "guard_audit_retention_holds",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_guard_hold_range"),
    )
    op.create_index("ix_guard_audit_retention_holds_workspace_id", "guard_audit_retention_holds", ["workspace_id"])
    for table in ("guard_audit_archive_segments", "guard_audit_retention_holds"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"""CREATE POLICY {table}_workspace ON {table}
            USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
            WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)""")
    op.add_column("guard_audit_events", sa.Column("archive_segment_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_guard_audit_event_archive_workspace", "guard_audit_events", "guard_audit_archive_segments",
                          ["archive_segment_id", "workspace_id"], ["id", "workspace_id"], ondelete="RESTRICT")
    op.create_index("ix_guard_audit_events_unarchived", "guard_audit_events", ["workspace_id", "ts", "id"],
                    postgresql_where=sa.text("archive_segment_id IS NULL"))


def downgrade():
    # Refuse to decide from an RLS-filtered view of archive metadata.
    # A migration role without BYPASSRLS must fail rather than erase it.
    op.execute("SET LOCAL row_security = off")
    if op.get_bind().execute(sa.text("SELECT EXISTS (SELECT 1 FROM guard_audit_archive_segments)")).scalar():
        raise RuntimeError("Restore archived payloads before removing audit archive metadata")
    op.drop_index("ix_guard_audit_events_unarchived", table_name="guard_audit_events")
    op.drop_constraint("fk_guard_audit_event_archive_workspace", "guard_audit_events", type_="foreignkey")
    op.drop_column("guard_audit_events", "archive_segment_id")
    op.drop_table("guard_audit_retention_holds")
    op.drop_table("guard_audit_archive_segments")
