"""OAuth 2.1 authorization code + DCR — new tables (#1734 sub-6 item 4).

Two tables added:

- oauth_clients: RFC 7591 Dynamic Client Registration entries. One row per
  MCP client that self-registers (Claude Desktop, Cursor, etc.). Public
  clients only for now (no client_secret) — PKCE is the auth mechanism.

- oauth_auth_codes: short-lived state for the authorization-code flow.
  Two lifecycle states in one row: 'pending' after /authorize before Clerk
  sign-in, 'issued' after /authorize/confirm mints the code, 'consumed' after
  /oauth/token redeems it. Not deleted on consume so replay attacks are
  detectable (used_at is set); purge task can drop expired rows later.

Revision ID: 0118
Revises: 0117
Create Date: 2026-09-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0118"
down_revision = "0117"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.Text(), primary_key=True),
        sa.Column("client_name", sa.Text(), nullable=False),
        sa.Column("redirect_uris", JSONB(), nullable=False),
        sa.Column("grant_types", JSONB(), nullable=False,
                  server_default=sa.text("'[\"authorization_code\", \"refresh_token\"]'::jsonb")),
        sa.Column("token_endpoint_auth_method", sa.Text(), nullable=False, server_default="none"),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("created_by_clerk_user_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "oauth_auth_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("code_hash", sa.Text(), nullable=True),  # sha256(raw code); NULL before /confirm
        sa.Column("client_id", sa.Text(),
                  sa.ForeignKey("oauth_clients.client_id", name="fk_oauth_auth_codes_client"),
                  nullable=False),
        sa.Column("redirect_uri", sa.Text(), nullable=False),
        sa.Column("code_challenge", sa.Text(), nullable=False),
        sa.Column("code_challenge_method", sa.Text(), nullable=False, server_default="S256"),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("scope", sa.Text(), nullable=True),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'issued', 'consumed')",
            name="ck_oauth_auth_codes_status",
        ),
    )
    # Unique on code_hash when set — one code, one row (replay detection).
    op.create_index(
        "ix_oauth_auth_codes_code_hash",
        "oauth_auth_codes",
        ["code_hash"],
        unique=True,
        postgresql_where=sa.text("code_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_oauth_auth_codes_expires_at",
        "oauth_auth_codes",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_oauth_auth_codes_expires_at", table_name="oauth_auth_codes")
    op.drop_index("ix_oauth_auth_codes_code_hash", table_name="oauth_auth_codes")
    op.drop_table("oauth_auth_codes")
    op.drop_table("oauth_clients")
