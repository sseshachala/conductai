"""
Email sending utility — Resend (preferred) or SendGrid.

Resolution order for credentials:
1. Workspace email credential (stored in integrations table)
2. Platform-level RESEND_API_KEY env var
Silently skips sending if neither is configured.
"""
import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

log = logging.getLogger(__name__)

APP_URL = "https://conductai.ai"


@dataclass
class EmailCredential:
    resend_api_key: str | None
    sendgrid_api_key: str | None
    from_name: str
    from_email: str


def _platform_credential() -> EmailCredential | None:
    if settings.resend_api_key:
        parts = settings.email_from.split("<")
        from_name = parts[0].strip() if len(parts) > 1 else "Conduct AI"
        from_email = parts[-1].rstrip(">").strip() if len(parts) > 1 else settings.email_from
        return EmailCredential(
            resend_api_key=settings.resend_api_key,
            sendgrid_api_key=None,
            from_name=from_name,
            from_email=from_email,
        )
    return None


def _workspace_credential(workspace_id: str, db) -> EmailCredential | None:
    """Load email credential stored in the workspace's integrations."""
    try:
        from app.models.integration import Integration
        from app.core.crypto import decrypt
        row = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.service == "email",
        ).first()
        if not row or not row.encrypted_credentials:
            return None
        creds = decrypt(row.encrypted_credentials)
        resend = creds.get("resend_api_key", "").strip()
        sendgrid = creds.get("sendgrid_api_key", "").strip()
        if not resend and not sendgrid:
            return None
        return EmailCredential(
            resend_api_key=resend or None,
            sendgrid_api_key=sendgrid or None,
            from_name=creds.get("from_name", "").strip() or "Conduct AI",
            from_email=creds.get("from_email", "").strip() or "notifications@conductai.ai",
        )
    except Exception as e:
        log.warning("Could not load workspace email credential: %s", e)
        return None


def _send_via_resend(api_key: str, from_addr: str, to: str, subject: str, html: str) -> bool:
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": from_addr, "to": [to], "subject": subject, "html": html},
            timeout=10,
        )
        if not r.is_success:
            log.warning("Resend error %s: %s", r.status_code, r.text[:200])
        return r.is_success
    except Exception as e:
        log.warning("Resend send failed: %s", e)
        return False


def _send_via_sendgrid(api_key: str, from_name: str, from_email: str, to: str, subject: str, html: str) -> bool:
    try:
        r = httpx.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "personalizations": [{"to": [{"email": to}]}],
                "from": {"email": from_email, "name": from_name},
                "subject": subject,
                "content": [{"type": "text/html", "value": html}],
            },
            timeout=10,
        )
        if not r.is_success:
            log.warning("SendGrid error %s: %s", r.status_code, r.text[:200])
        return r.is_success
    except Exception as e:
        log.warning("SendGrid send failed: %s", e)
        return False


def send_email(*, to: str, subject: str, html: str, workspace_id: str | None = None, db=None) -> bool:
    """Send an email using workspace credential or platform fallback. Returns True on success."""
    cred: EmailCredential | None = None
    if workspace_id and db:
        cred = _workspace_credential(workspace_id, db)
    if not cred:
        cred = _platform_credential()
    if not cred:
        log.info("No email credential configured — skipping send to %s", to)
        return False

    from_addr = f"{cred.from_name} <{cred.from_email}>"

    if cred.resend_api_key:
        return _send_via_resend(cred.resend_api_key, from_addr, to, subject, html)
    if cred.sendgrid_api_key:
        return _send_via_sendgrid(cred.sendgrid_api_key, cred.from_name, cred.from_email, to, subject, html)
    return False


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

def invite_email_html(
    *,
    workspace_name: str,
    invited_by_email: str | None,
    role: str,
) -> str:
    inviter_line = (
        f"<b>{invited_by_email}</b> has invited you"
        if invited_by_email
        else "You've been invited"
    )
    role_descriptions = {
        "admin":  "Full access — manage members, credentials, environments, and agents.",
        "editor": "Can run agents, edit workflows, and manage credentials.",
        "viewer": "Read-only access — view runs, workflows, and settings.",
    }
    role_desc = role_descriptions.get(role, "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>You're invited to {workspace_name} on Conduct AI</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f4;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f4;padding:40px 0;">
    <tr>
      <td align="center">
        <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">

          <!-- Logo -->
          <tr>
            <td align="center" style="padding-bottom:24px;">
              <span style="font-size:20px;font-weight:700;color:#1c1917;letter-spacing:-0.5px;">Conduct AI</span>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td style="background:#ffffff;border-radius:16px;border:1px solid #e7e5e4;padding:40px 40px 32px;">

              <!-- Heading -->
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#1c1917;line-height:1.3;">
                You're invited to join<br /><span style="color:#4f46e5;">{workspace_name}</span>
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:#78716c;line-height:1.6;">
                {inviter_line} to collaborate on <b>{workspace_name}</b> on Conduct AI —
                the platform for agentic GitHub and DevOps workflows.
              </p>

              <!-- Role badge -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;">
                    <p style="margin:0 0 2px;font-size:12px;font-weight:600;color:#15803d;text-transform:uppercase;letter-spacing:0.5px;">Your role</p>
                    <p style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1c1917;text-transform:capitalize;">{role}</p>
                    <p style="margin:0;font-size:12px;color:#57534e;">{role_desc}</p>
                  </td>
                </tr>
              </table>

              <!-- CTA -->
              <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
                <tr>
                  <td align="center" style="border-radius:10px;background:#1c1917;">
                    <a href="{APP_URL}/sign-in"
                       style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#ffffff;text-decoration:none;border-radius:10px;">
                      Accept invitation →
                    </a>
                  </td>
                </tr>
              </table>

              <!-- How it works -->
              <table cellpadding="0" cellspacing="0" style="background:#fafaf9;border:1px solid #e7e5e4;border-radius:10px;padding:16px;margin-bottom:8px;width:100%;">
                <tr>
                  <td>
                    <p style="margin:0 0 8px;font-size:12px;font-weight:600;color:#57534e;text-transform:uppercase;letter-spacing:0.5px;">How it works</p>
                    <p style="margin:0;font-size:13px;color:#78716c;line-height:1.7;">
                      1. Click <b>Accept invitation</b> above<br />
                      2. Sign in or create an account using <b>this email address</b><br />
                      3. You'll automatically be added to <b>{workspace_name}</b>
                    </p>
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 0 0;text-align:center;">
              <p style="margin:0;font-size:12px;color:#a8a29e;">
                This invitation was sent by Conduct AI · <a href="{APP_URL}" style="color:#a8a29e;">{APP_URL}</a><br />
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
