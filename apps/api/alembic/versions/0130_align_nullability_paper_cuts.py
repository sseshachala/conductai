"""Align four columns' nullability between prod and the ORM.

Audit against prod (2026-09-15) turned up four columns where prod and the
ORM disagree — all pre-existing legacy state, no active harm. Fixing so the
schema-drift regression test stays green and so a future migration doesn't
trip over the same "prod says X, model says Y" mismatch.

Three timestamp columns are already NOT NULL in the ORM but NULL in prod
(a NOT NULL tighten shipped without a paired backfill; existing rows kept
their NULLs). Backfill any residual NULLs with now() then SET NOT NULL.

  - email_templates.updated_at
  - workspace_invites.created_at
  - workspace_users.joined_at

One column (projects.slug) is NOT NULL in prod but nullable in the ORM.
Every code path already computes a slug via _unique_slug() before insert,
so tightening the ORM matches actual behaviour. This migration also SETs
NOT NULL on prod idempotently — no-op there, but keeps fresh-build DBs
in sync.

Revision ID: 0130
Revises: 0129
"""
from alembic import op

revision = "0130"
down_revision = "0129"
branch_labels = None
depends_on = None


def upgrade():
    # Backfill any pre-existing NULL rows so the SET NOT NULL below doesn't
    # error out. Expected row count = 0 in most environments; the UPDATE
    # is cheap either way and safe to run repeatedly.
    op.execute("UPDATE email_templates    SET updated_at = now() WHERE updated_at IS NULL")
    op.execute("UPDATE workspace_invites  SET created_at = now() WHERE created_at IS NULL")
    op.execute("UPDATE workspace_users    SET joined_at  = now() WHERE joined_at  IS NULL")

    # Idempotent tightens — no-op on prod for slug (already NOT NULL) and
    # a genuine change for the three timestamps.
    op.execute("ALTER TABLE email_templates    ALTER COLUMN updated_at SET NOT NULL")
    op.execute("ALTER TABLE workspace_invites  ALTER COLUMN created_at SET NOT NULL")
    op.execute("ALTER TABLE workspace_users    ALTER COLUMN joined_at  SET NOT NULL")
    op.execute("ALTER TABLE projects           ALTER COLUMN slug        SET NOT NULL")


def downgrade():
    op.execute("ALTER TABLE email_templates    ALTER COLUMN updated_at DROP NOT NULL")
    op.execute("ALTER TABLE workspace_invites  ALTER COLUMN created_at DROP NOT NULL")
    op.execute("ALTER TABLE workspace_users    ALTER COLUMN joined_at  DROP NOT NULL")
    op.execute("ALTER TABLE projects           ALTER COLUMN slug        DROP NOT NULL")
