"""Create model_routing_policies table and seed from hardcoded policy dict

Revision ID: 0007
Revises: 0006
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_SEED = [
    # (category, preference, provider, model_id, reason)
    ("code_implementation", "quality",  "anthropic", "claude-opus-4-7",           "code implementation benefits from strongest reasoning"),
    ("code_implementation", "balanced", "anthropic", "claude-sonnet-4-6",          "balanced model for code implementation"),
    ("code_implementation", "speed",    "anthropic", "claude-sonnet-4-6",          "sonnet is fast enough for code tasks"),
    ("code_implementation", "cost",     "openai",    "gpt-4.1-mini",               "cost-efficient model for code implementation"),
    ("code_review",         "quality",  "anthropic", "claude-opus-4-7",           "code review benefits from strongest reasoning model"),
    ("code_review",         "balanced", "anthropic", "claude-sonnet-4-6",          "balanced model for code review"),
    ("code_review",         "speed",    "openai",    "gpt-4.1-mini",               "fast and efficient for code review"),
    ("code_review",         "cost",     "openai",    "gpt-4.1-mini",               "cost-efficient for structured code review output"),
    ("security",            "quality",  "anthropic", "claude-opus-4-7",           "security scanning requires highest-precision model"),
    ("security",            "balanced", "anthropic", "claude-opus-4-7",           "security scanning: quality always preferred over cost"),
    ("security",            "speed",    "anthropic", "claude-sonnet-4-6",          "sonnet for security when speed is prioritized"),
    ("security",            "cost",     "anthropic", "claude-sonnet-4-6",          "sonnet minimum viable for security"),
    ("triage",              "quality",  "anthropic", "claude-sonnet-4-6",          "sonnet sufficient for structured triage tasks"),
    ("triage",              "balanced", "openai",    "gpt-4.1-mini",               "balanced and efficient for triage"),
    ("triage",              "speed",    "openai",    "gpt-4.1-mini",               "fast triage classification"),
    ("triage",              "cost",     "openai",    "gpt-4.1-mini",               "cost-optimal for simple triage tasks"),
    ("summarization",       "quality",  "anthropic", "claude-sonnet-4-6",          "sonnet more than sufficient for summarization"),
    ("summarization",       "balanced", "openai",    "gpt-4.1-mini",               "balanced model for summarization"),
    ("summarization",       "speed",    "openai",    "gpt-4.1-mini",               "fast summarization"),
    ("summarization",       "cost",     "openai",    "gpt-4.1-mini",               "cost-optimal for summarization"),
    ("reasoning",           "quality",  "anthropic", "claude-opus-4-7",           "reasoning tasks benefit from strongest model"),
    ("reasoning",           "balanced", "anthropic", "claude-sonnet-4-6",          "balanced model for reasoning tasks"),
    ("reasoning",           "speed",    "anthropic", "claude-sonnet-4-6",          "sonnet balances speed and reasoning depth"),
    ("reasoning",           "cost",     "openai",    "gpt-4.1-mini",               "cost-efficient minimum viable reasoning"),
    # fallback rows (empty category = default for unknown playbooks)
    ("",                    "quality",  "anthropic", "claude-opus-4-7",           "quality preference: strongest model"),
    ("",                    "balanced", "anthropic", "claude-sonnet-4-6",          "balanced preference: default model"),
    ("",                    "speed",    "openai",    "gpt-4.1-mini",               "speed preference: efficient model"),
    ("",                    "cost",     "openai",    "gpt-4.1-mini",               "cost preference: efficient model"),
]


def upgrade() -> None:
    op.create_table(
        "model_routing_policies",
        sa.Column("id",         sa.Integer(),     primary_key=True, autoincrement=True),
        sa.Column("category",   sa.Text(),        nullable=False, server_default=""),
        sa.Column("preference", sa.Text(),        nullable=False),
        sa.Column("provider",   sa.Text(),        nullable=False),
        sa.Column("model_id",   sa.Text(),        nullable=False),
        sa.Column("reason",     sa.Text(),        nullable=False, server_default=""),
        sa.Column("enabled",    sa.Boolean(),     nullable=False, server_default="true"),
    )
    op.create_unique_constraint(
        "uq_routing_category_preference",
        "model_routing_policies",
        ["category", "preference"],
    )

    conn = op.get_bind()
    conn.execute(
        text(
            "INSERT INTO model_routing_policies (category, preference, provider, model_id, reason) "
            "VALUES (:category, :preference, :provider, :model_id, :reason)"
        ),
        [
            {"category": c, "preference": p, "provider": prov, "model_id": m, "reason": r}
            for c, p, prov, m, r in _SEED
        ],
    )


def downgrade() -> None:
    op.drop_table("model_routing_policies")
