"""0027 project_slug — add slug column to projects, backfill from name

Revision ID: 0027
Revises: 0026
"""
import re
from alembic import op
import sqlalchemy as sa

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def upgrade():
    op.add_column("projects", sa.Column("slug", sa.String(100), nullable=True))

    # Backfill slugs from existing names, de-duplicating with a numeric suffix
    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, name FROM projects ORDER BY created_at")).fetchall()
    seen: dict[str, int] = {}
    for row in rows:
        base = _slugify(row.name) or "project"
        if base not in seen:
            slug = base
        else:
            seen[base] += 1
            slug = f"{base}-{seen[base]}"
        seen.setdefault(base, 0)
        conn.execute(
            sa.text("UPDATE projects SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": str(row.id)},
        )

    op.alter_column("projects", "slug", nullable=False)
    op.create_unique_constraint("uq_projects_slug_workspace", "projects", ["workspace_id", "slug"])


def downgrade():
    op.drop_constraint("uq_projects_slug_workspace", "projects", type_="unique")
    op.drop_column("projects", "slug")
