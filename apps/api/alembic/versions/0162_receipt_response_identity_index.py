"""Index scoped protocol response IDs without changing existing receipts."""
from alembic import op
import sqlalchemy as sa

revision = "0162"
down_revision = "0161"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_llm_attempt_receipts_ws_response_id", "llm_attempt_receipts",
                    ["workspace_id", sa.text("(calculation_provenance ->> 'provider_response_id')")])


def downgrade():
    op.drop_index("ix_llm_attempt_receipts_ws_response_id", table_name="llm_attempt_receipts")
