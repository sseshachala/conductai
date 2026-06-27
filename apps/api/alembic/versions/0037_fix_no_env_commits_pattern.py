"""Fix no-env-commits rule regex in conduct-base skill pack

Revision ID: 0037_fix_no_env_commits_pattern
Revises: 0036_guard_rule_override_match_pattern
Create Date: 2026-06-27
"""
from alembic import op

revision = "0037_fix_no_env_commits_pattern"
down_revision = "0036_guard_rule_override_match_pattern"
branch_labels = None
depends_on = None

# Single-escaped for Python string, double-escaped for JSONB string value
NEW = r"git add\b.*(\s|/)\.env(\.[a-zA-Z]+)?(\s|$)"
OLD = r"git (add|commit).+\.env"


def _update(pattern: str) -> str:
    # Escape single quotes for SQL, embed as JSON string literal
    safe = pattern.replace("'", "''")
    return f"""
        UPDATE skill_packs
        SET rules = (
            SELECT jsonb_agg(
                CASE
                    WHEN rule->>'id' = 'no-env-commits'
                    THEN jsonb_set(rule, '{{match_pattern}}', to_jsonb('{safe}'::text))
                    ELSE rule
                END
            )
            FROM jsonb_array_elements(rules) AS rule
        )
        WHERE slug = 'conduct-base'
    """


def upgrade() -> None:
    op.execute(_update(NEW))


def downgrade() -> None:
    op.execute(_update(OLD))
