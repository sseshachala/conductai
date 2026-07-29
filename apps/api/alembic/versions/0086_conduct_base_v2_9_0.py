"""fix(guard): conduct-base v2.9.0 — tighten proxy-no-credential-leak regex

Old regex matched bare env var names (DATABASE_URL, DB_PASSWORD,
STRIPE_SECRET, AWS_SECRET_ACCESS_KEY) as a word — so any workflow whose
subject IS security (threat modeler, secret scanner, docs generator)
false-positived on legitimate discussion of secrets by name.

New regex requires either:
  - A real value context: NAME = value with ≥6 non-whitespace chars
  - Or a value-shaped pattern that already implies a real credential
    (postgres:// URL with something after, sk_live_XXX, sk-ant-XXX, AKIA...,
    ghp_...)

Actual credential leaks still blocked. Text like "DATABASE_URL is exposed"
no longer false-triggers.

Related issues:
  - conductai#1000 (threat-modeler testbed run — blocked by this)
  - conductai#1003 close comment (data-vs-action inspection is the deeper
    fix; regex tightening here is the tactical unblock)

Revision ID: 0086
Revises: 0085
Create Date: 2026-07-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0086"
down_revision = "0085"
branch_labels = None
depends_on = None


# New tightened pattern for proxy-no-credential-leak (single source of truth
# lives in apps/api/app/modules/guard/skill_packs/conduct-base.json — this
# migration keeps the DB in sync).
_NEW_PATTERN = (
    r"(postgres(?:ql)?://\S+|mysql://\S+|"
    r"sk_live_[0-9a-zA-Z]{20,}|sk-ant-[a-zA-Z0-9\-]{20,}|"
    r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36,}|"
    r"(DATABASE_URL|DB_PASSWORD|STRIPE_SECRET|AWS_SECRET_ACCESS_KEY)\s*=\s*['\"]?[^\s'\"]{6,})"
)

_OLD_PATTERN = (
    r"(DATABASE_URL|postgres(?:ql)?://|mysql://|DB_PASSWORD|STRIPE_SECRET|"
    r"sk_live_[0-9a-zA-Z]{20,}|sk-ant-[a-zA-Z0-9\-]{20,}|"
    r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{36,}|AWS_SECRET_ACCESS_KEY)"
)


def _rewrite_pattern(conn, old: str, new: str) -> None:
    """Rewrite proxy-no-credential-leak match_pattern across every conduct-base
    version row + the active cache. Safer than inserting a new version — every
    workspace using any older version gets the fix immediately, no re-sync."""
    conn.execute(
        sa.text(
            """
            UPDATE skill_packs
               SET rules = (
                 SELECT jsonb_agg(
                   CASE WHEN r->>'id' = 'proxy-no-credential-leak'
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
    # Bump/insert the 2.9.0 row so version-aware clients pick it up.
    conn.execute(
        sa.text(
            """
            INSERT INTO skill_packs (slug, version, name, tier, description, rules)
            SELECT 'conduct-base', '2.9.0', name, tier, description, rules
              FROM skill_packs
             WHERE slug = 'conduct-base'
             ORDER BY published_at DESC NULLS LAST, version DESC
             LIMIT 1
            ON CONFLICT (slug, version) DO UPDATE SET rules = EXCLUDED.rules
            """
        )
    )
    # Invalidate every workspace's policy cache so the new pattern loads on
    # next request. Cheap — cache repopulates on demand.
    conn.execute(sa.text("DELETE FROM guard_policy_cache"))


def upgrade() -> None:
    _rewrite_pattern(op.get_bind(), _OLD_PATTERN, _NEW_PATTERN)


def downgrade() -> None:
    _rewrite_pattern(op.get_bind(), _NEW_PATTERN, _OLD_PATTERN)
    op.get_bind().execute(
        sa.text("DELETE FROM skill_packs WHERE slug = 'conduct-base' AND version = '2.9.0'")
    )
