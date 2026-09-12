"""backfill agent_identities.source per creator (Identities Option C prep)

Data-only migration — no schema change. The `source` column already exists
(added in migration 0090) but every non-Okta creator was using the default
"conduct" value. That made `source` useless as a discriminator between
trial / CLI-minted / auto-provisioned / manually-created identities.

Going forward, each creator sets its own explicit `source`:
  - trial_seed.py       -> "conduct_trial"
  - cli_token.py        -> "conduct_cli"
  - mint_agent_identity -> "conduct_auto" (default; used by guard join flow)
  - create endpoint     -> "conduct_api"
  - okta_sync.py        -> "okta_jwt" (unchanged)

Backfill existing rows by inferring source from the name pattern the
respective creator historically used. Anything that doesn't match a
pattern stays as "conduct" — safe legacy catchall for pre-normalization
manually-created rows.

Revision ID: 0122
Revises: 0121
Create Date: 2026-09-12
"""
from alembic import op


revision = "0122"
down_revision = "0121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Trials — exact name match set by trial_seed.py.
    op.execute(
        "UPDATE agent_identities SET source = 'conduct_trial' "
        "WHERE source = 'conduct' AND name = 'Trial (7 days)'"
    )
    # CLI-minted — name suffix set by cli_token.py.
    op.execute(
        "UPDATE agent_identities SET source = 'conduct_cli' "
        "WHERE source = 'conduct' AND name LIKE '%% (CLI)'"
    )
    # Auto-provisioned via guard join flow — name suffix set by config.py.
    op.execute(
        "UPDATE agent_identities SET source = 'conduct_auto' "
        "WHERE source = 'conduct' AND name LIKE '%% (auto)'"
    )


def downgrade() -> None:
    # Reverse — collapse the three explicit values back to the legacy default.
    op.execute(
        "UPDATE agent_identities SET source = 'conduct' "
        "WHERE source IN ('conduct_trial', 'conduct_cli', 'conduct_auto')"
    )
