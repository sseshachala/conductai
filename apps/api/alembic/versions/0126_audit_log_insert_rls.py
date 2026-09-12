"""Harden tenant RLS and allow tenant-scoped audit log inserts.

Revision ID: 0126
Revises: 0125
Create Date: 2026-09-12
"""
from alembic import op


revision = "0126"
down_revision = "0125"
branch_labels = None
depends_on = None


_TABLES = [
    "workflows",
    "audit_log",
    "watchdog_events",
]


_SAFE_WORKSPACE = (
    "NULLIF(current_setting('app.current_workspace', true), '')::uuid"
)


def upgrade() -> None:
    # SET LOCAL resets custom settings to an empty string on pooled connections.
    # NULLIF keeps requests without workspace context from failing UUID casts.
    for table in _TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            AS PERMISSIVE FOR SELECT
            USING (workspace_id = {_SAFE_WORKSPACE})
        """)
    op.execute("""
        CREATE POLICY tenant_insert ON audit_log
        AS PERMISSIVE FOR INSERT
        WITH CHECK (
            workspace_id = NULLIF(
                current_setting('app.current_workspace', true), ''
            )::uuid
        )
    """)


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_insert ON audit_log")
    for table in _TABLES:
        op.execute(f"DROP POLICY tenant_isolation ON {table}")
        op.execute(f"""
            CREATE POLICY tenant_isolation ON {table}
            AS PERMISSIVE FOR SELECT
            USING (
                workspace_id = current_setting(
                    'app.current_workspace', true
                )::uuid
            )
        """)
