"""Fix no-env-commits rule regex in conduct-base skill pack

Revision ID: 0037_fix_no_env_commits_pattern
Revises: 0036_guard_rule_override_match_pattern
Create Date: 2026-06-27
"""
from alembic import op
from sqlalchemy.sql import text

revision = "0037_fix_no_env_commits_pattern"
down_revision = "0036_guard_rule_override_match_pattern"
branch_labels = None
depends_on = None

OLD = "git (add|commit).+\\\\.env"
NEW = "git add\\\\b.*(\\\\s|/)\\\\.env(\\\\.[a-zA-Z]+)?(\\\\s|$)"


def upgrade() -> None:
    op.execute(text("""
        UPDATE skill_packs
        SET rules = (
            SELECT jsonb_agg(
                CASE
                    WHEN rule->>'id' = 'no-env-commits'
                    THEN jsonb_set(rule, '{match_pattern}', :new_pat::jsonb)
                    ELSE rule
                END
            )
            FROM jsonb_array_elements(rules) AS rule
        )
        WHERE slug = 'conduct-base'
    """).bindparams(new_pat=f'"{NEW}"'))


def downgrade() -> None:
    op.execute(text("""
        UPDATE skill_packs
        SET rules = (
            SELECT jsonb_agg(
                CASE
                    WHEN rule->>'id' = 'no-env-commits'
                    THEN jsonb_set(rule, '{match_pattern}', :old_pat::jsonb)
                    ELSE rule
                END
            )
            FROM jsonb_array_elements(rules) AS rule
        )
        WHERE slug = 'conduct-base'
    """).bindparams(old_pat=f'"{OLD}"'))
