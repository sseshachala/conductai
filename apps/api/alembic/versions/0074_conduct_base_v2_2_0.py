"""feat(guard): conduct-base v2.2.0 — add workflow to match_tool for dangerous-ops rules

Revision ID: 0074
Revises: 0073
Create Date: 2026-07-14
"""
import json
import pathlib
from alembic import op

revision = "0074"
down_revision = "0073"
branch_labels = None
depends_on = None

_PACK_PATH = pathlib.Path(__file__).parents[3] / "app/modules/guard/skill_packs/conduct-base.json"


def upgrade():
    data = json.loads(_PACK_PATH.read_text())
    rules_json = json.dumps(data["rules"])
    op.execute(f"""
        INSERT INTO skill_packs (slug, version, name, tier, description, rules)
        VALUES (
            'conduct-base', '2.2.0', 'Conduct Base', 'free',
            'Core AI governance rules — proxy interception, agent safety, and surface-aware enforcement across all AI tools. 3 proxy + 13 agent + 7 surface rules.',
            '{rules_json.replace("'", "''")}'::jsonb
        )
        ON CONFLICT (slug, version) DO UPDATE SET rules = EXCLUDED.rules;
    """)
    # Invalidate cached policy for all workspaces so next run picks up new rules
    op.execute("DELETE FROM guard_policy_cache;")


def downgrade():
    op.execute("DELETE FROM skill_packs WHERE slug = 'conduct-base' AND version = '2.2.0';")
    op.execute("DELETE FROM guard_policy_cache;")
