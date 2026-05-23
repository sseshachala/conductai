"""add email_templates table with seed data

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WORKSPACE_INVITE_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>You're invited to {{ workspace_name }} on Conduct AI</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f4;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

          <tr>
            <td align="center" style="padding-bottom:24px;">
              <span style="font-size:20px;font-weight:700;color:#1c1917;letter-spacing:-0.5px;">Conduct AI</span>
            </td>
          </tr>

          <tr>
            <td style="background:#ffffff;border-radius:16px;border:1px solid #e7e5e4;padding:40px 40px 32px;">

              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#1c1917;line-height:1.3;">
                You're invited to join<br /><span style="color:#4f46e5;">{{ workspace_name }}</span>
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:#78716c;line-height:1.6;">
                {% if invited_by_email %}<b>{{ invited_by_email }}</b> has invited you{% else %}You've been invited{% endif %}
                to collaborate on <b>{{ workspace_name }}</b> on Conduct AI —
                the platform for agentic GitHub and DevOps workflows.
              </p>

              <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;">
                    <p style="margin:0 0 2px;font-size:12px;font-weight:600;color:#15803d;text-transform:uppercase;letter-spacing:0.5px;">Your role</p>
                    <p style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1c1917;text-transform:capitalize;">{{ role }}</p>
                    <p style="margin:0;font-size:12px;color:#57534e;">{{ role_description }}</p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td align="center" style="border-radius:10px;background:#1c1917;">
                    <a href="{{ app_url }}/sign-in"
                       style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px;">
                      Accept invitation →
                    </a>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" style="background:#fafaf9;border:1px solid #e7e5e4;border-radius:10px;padding:16px;width:100%;">
                <tr>
                  <td>
                    <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#57534e;text-transform:uppercase;letter-spacing:0.5px;">How it works</p>
                    <p style="margin:0;font-size:13px;color:#78716c;line-height:1.7;">
                      1. Click <b>Accept invitation</b> above<br />
                      2. Sign in or create an account using <b>this email address</b><br />
                      3. You'll automatically be added to <b>{{ workspace_name }}</b>
                    </p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <tr>
            <td style="padding:20px 0 0;text-align:center;">
              <p style="margin:0;font-size:12px;color:#a8a29e;">
                Sent by Conduct AI · <a href="{{ app_url }}" style="color:#a8a29e;">{{ app_url }}</a><br />
                If you weren't expecting this, you can safely ignore this email.
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def upgrade() -> None:
    op.create_table(
        "email_templates",
        sa.Column("slug", sa.String(100), primary_key=True),
        sa.Column("subject", sa.Text, nullable=False),
        sa.Column("html_body", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("variables", sa.JSON, nullable=True),  # list of variable names for docs
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    op.execute("""
        INSERT INTO email_templates (slug, subject, html_body, description, variables) VALUES (
            'workspace_invite',
            'You''re invited to {{ workspace_name }} on Conduct AI',
            :html,
            'Sent when an admin invites a new member to a workspace by email.',
            '["workspace_name", "invited_by_email", "role", "role_description", "app_url"]'
        )
    """, {"html": WORKSPACE_INVITE_HTML})


def downgrade() -> None:
    op.drop_table("email_templates")
