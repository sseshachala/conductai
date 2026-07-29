"""fix(guard): conduct-base v2.10.0 — tighten workflow-block-destructive regex

Old pattern matched a bare `delete` word inside prose or Python kwargs,
so a threat-model block whose output described
`NamedTemporaryFile(delete=False)` tripped the block. Same class of bug
as `proxy-no-credential-leak` in migration 0086 — data-vs-action
inspection gap where Guard scans state content with an
action-name-shaped pattern.

New pattern requires destructive context, not a bare word:
- SQL:   DELETE FROM, DROP TABLE|DATABASE|SCHEMA|INDEX, TRUNCATE TABLE
- HTTP:  -X DELETE, method='DELETE'
- Shell: rm -rf, git push --force, git branch -D
- Names: nuke*, teardown_*, purge_*, destroy_*, wipe_*, delete_*
  (compound names only — bare "delete"/"purge"/"destroy" no longer match)

Verified against 15 real destructive samples (all catch) and 5
threat-model-prose false positives (all pass). See test in
apps/api/scripts (or the ephemeral session log).

Related issues:
  - conductai#1000 (threat-modeler testbed run — blocked by this)
  - conductai#1003 (Guard UX + data-vs-action inspection — deeper fix
    tracked there; this migration is the tactical unblock)

Revision ID: 0088
Revises: 0087
Create Date: 2026-07-29
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0088"
down_revision = "0087"
branch_labels = None
depends_on = None


# Source of truth for the new pattern lives in
# apps/api/app/modules/guard/skill_packs/conduct-base.json — this migration
# keeps every existing row and the workspace policy cache in sync.
_NEW_PATTERN = (
    r"(?:\bDELETE\s+FROM\b|"
    r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA|INDEX)\b|"
    r"\bTRUNCATE\s+TABLE\b|"
    r"-X\s+DELETE\b|"
    r"method\s*[:=]\s*['\"]DELETE|"
    r"\brm\s+-rf\b|"
    r"\bgit\s+push\s+--force\b|"
    r"\bgit\s+branch\s+-D\b|"
    r"\bnuke[_\-]?\w*|"
    r"\bteardown[_\-]\w+|"
    r"\bpurge[_\-]\w+|"
    r"\bdestroy[_\-]\w+|"
    r"\bwipe[_\-]\w+|"
    r"\bdelete[_\-]\w+)"
)

_OLD_PATTERN = r"delete|drop[_\-]|purge|destroy|wipe[_\-]|nuke|teardown"


def _rewrite_pattern(conn, new: str) -> None:
    """Rewrite workflow-block-destructive match_pattern across every
    conduct-base version row + invalidate the workspace policy cache."""
    conn.execute(
        sa.text(
            """
            UPDATE skill_packs
               SET rules = (
                 SELECT jsonb_agg(
                   CASE WHEN r->>'id' = 'workflow-block-destructive'
                        THEN jsonb_set(r, '{match_pattern}', to_jsonb(CAST(:new AS text)))
                        ELSE r
                   END
                 )
                 FROM jsonb_array_elements(rules) r
               )
             WHERE slug = 'conduct-base'
            """
        ),
        {"new": new},
    )
    # Insert the 2.10.0 version row so version-aware clients pick it up.
    conn.execute(
        sa.text(
            """
            INSERT INTO skill_packs (slug, version, name, tier, description, rules)
            SELECT 'conduct-base', '2.10.0', name, tier, description, rules
              FROM skill_packs
             WHERE slug = 'conduct-base'
             ORDER BY published_at DESC NULLS LAST, version DESC
             LIMIT 1
            ON CONFLICT (slug, version) DO UPDATE SET rules = EXCLUDED.rules
            """
        )
    )
    # Invalidate every workspace's policy cache so the new pattern loads on
    # the next guard_check request.
    conn.execute(sa.text("DELETE FROM guard_policy_cache"))


def upgrade() -> None:
    _rewrite_pattern(op.get_bind(), _NEW_PATTERN)


def downgrade() -> None:
    _rewrite_pattern(op.get_bind(), _OLD_PATTERN)
    op.get_bind().execute(
        sa.text("DELETE FROM skill_packs WHERE slug = 'conduct-base' AND version = '2.10.0'")
    )
