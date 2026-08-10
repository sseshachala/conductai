"""Okta JWT auth config on integrations — issuer, audience, feature flag.

Bridge for #1056 (Okta Phase 3b). Adds three columns to `integrations`:

- okta_issuer    — the OAuth authorization-server `iss` we accept for JWTs
                    from this workspace. Indexed for reverse lookup
                    (given an unverified JWT iss, find the workspace).
- okta_audience  — the `aud` claim we require on those JWTs.
- okta_auth_enabled — per-workspace feature flag. Default OFF.

All three are nullable. Existing rows (non-Okta integrations, or Okta rows
without JWT auth configured) stay untouched. When okta_auth_enabled is
false or null, the verifier bridge returns None and callers fall through
to the existing Clerk/agent-token paths.

Revision ID: 0091
Revises: 0090
Create Date: 2026-08-10
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0091"
down_revision = "0090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("integrations", sa.Column("okta_issuer", sa.String(500), nullable=True))
    op.add_column("integrations", sa.Column("okta_audience", sa.String(500), nullable=True))
    op.add_column(
        "integrations",
        sa.Column("okta_auth_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "idx_integrations_okta_issuer",
        "integrations",
        ["okta_issuer"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_integrations_okta_issuer", table_name="integrations")
    op.drop_column("integrations", "okta_auth_enabled")
    op.drop_column("integrations", "okta_audience")
    op.drop_column("integrations", "okta_issuer")
