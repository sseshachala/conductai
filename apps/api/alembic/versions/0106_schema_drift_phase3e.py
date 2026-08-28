"""Phase 3e schema drift reconciliation — D3 + D4 + persona TEXT + runs.workspace_id FK

Revision ID: 0106
Revises: 0105
Create Date: 2026-08-28

Four functional fixes, all pre-existing model↔DB mismatches:

1. D3 — workspace_instructions unique constraint → unique index
   Model declares `Index("ix_workspace_instructions_workspace_id", "workspace_id",
   unique=True)` in __table_args__. DB has an auto-named UniqueConstraint on
   workspace_id (from migration 0085). Alembic considers these different object
   types. Drop the constraint (dynamic name lookup via pg_constraint), then
   create the unique index that matches the model. Wrapped in the migration's
   default transaction so uniqueness is never briefly unenforced.

2. D4 — security_findings drop source_project_id FK
   Model explicitly comments: "Scanner project that produced this finding —
   lineage only. Fix routing still uses ``repo_full_name``. See conductai#1005."
   DB still has the FK from migration 0087. Drop it to match model intent.

3. workspace_custom_rules.persona VARCHAR(32) → TEXT
   Model declares `Column(Text, nullable=False, default="agent")`. DB has
   VARCHAR(32) which was fine when persona was a single value but persona
   grew to comma-joined strings that can exceed 32 chars. VARCHAR→TEXT cast
   is implicit and lossless in Postgres; USING clause is a defensive belt.

4. runs.workspace_id ADD FK
   Model declares `ForeignKey("workspaces.id")`. DB missing the FK constraint
   (probably added to model post-hoc without paired migration). Pre-flight
   check: refuse to add if any orphan rows exist (workspace_id pointing at
   a workspaces.id that doesn't exist), else the FK creation would fail
   opaquely.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0106"
down_revision = "0105"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. D3 — workspace_instructions: UniqueConstraint → unique Index ──
    row = conn.execute(
        sa.text(
            """
            SELECT conname FROM pg_constraint
            WHERE conrelid = 'workspace_instructions'::regclass
              AND contype = 'u'
              AND conkey = ARRAY[(
                SELECT attnum FROM pg_attribute
                WHERE attrelid = 'workspace_instructions'::regclass
                  AND attname = 'workspace_id'
              )]::smallint[]
            LIMIT 1
            """
        )
    ).first()
    if row and row.conname:
        op.execute(
            f'ALTER TABLE workspace_instructions DROP CONSTRAINT "{row.conname}"'
        )
    # Create the unique index the model declares. `if_not_exists` guards
    # against a re-run where the constraint drop already happened but the
    # index create didn't (partial-migration recovery).
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_workspace_instructions_workspace_id "
        "ON workspace_instructions (workspace_id)"
    )

    # ── 2. D4 — security_findings: DROP source_project_id FK ──
    # Model comment (security_finding.py:15-17) marks this column lineage-only.
    op.execute(
        "ALTER TABLE security_findings "
        "DROP CONSTRAINT IF EXISTS security_findings_source_project_id_fkey"
    )

    # ── 3. workspace_custom_rules.persona VARCHAR(32) → TEXT ──
    op.execute(
        "ALTER TABLE workspace_custom_rules "
        "ALTER COLUMN persona TYPE text USING persona::text"
    )

    # ── 4. runs.workspace_id ADD FK ──
    # Defensive: refuse to add if any runs.workspace_id has no matching workspace.
    orphan_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*) FROM runs r
            LEFT JOIN workspaces w ON w.id = r.workspace_id
            WHERE w.id IS NULL
            """
        )
    ).scalar()
    if orphan_count:
        raise RuntimeError(
            f"Refusing to add FK on runs.workspace_id: {orphan_count} orphan "
            "row(s) reference a workspace that no longer exists. "
            "Clean up orphan runs first (DELETE, or backfill workspace_id)."
        )
    op.create_foreign_key(
        "runs_workspace_id_fkey",
        "runs",
        "workspaces",
        ["workspace_id"],
        ["id"],
    )


def downgrade() -> None:
    # 4. Drop runs.workspace_id FK
    op.drop_constraint("runs_workspace_id_fkey", "runs", type_="foreignkey")

    # 3. persona TEXT → VARCHAR(32) — lossy if any row now exceeds 32 chars
    op.execute(
        "ALTER TABLE workspace_custom_rules "
        "ALTER COLUMN persona TYPE varchar(32) USING substring(persona, 1, 32)"
    )

    # 2. Recreate D4 FK. Original migration 0087 declared no ondelete.
    op.execute(
        "ALTER TABLE security_findings "
        "ADD CONSTRAINT security_findings_source_project_id_fkey "
        "FOREIGN KEY (source_project_id) REFERENCES projects(id)"
    )

    # 1. Drop the unique index. UniqueConstraint is NOT restored (its name
    # was auto-generated so we can't recover it deterministically). If a
    # downgrade needs constraint-form uniqueness, follow-up migration required.
    op.execute(
        "DROP INDEX IF EXISTS ix_workspace_instructions_workspace_id"
    )
