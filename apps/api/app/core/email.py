"""
Email sending utility — Resend (preferred) or SendGrid.

Template resolution order:
1. email_templates table in DB (editable at runtime)
2. Hardcoded fallback (used on first boot before migration runs)

Credential resolution order:
1. Workspace email credential (stored in integrations table)
2. Platform-level RESEND_API_KEY / EMAIL_FROM env vars
"""
import logging
from dataclasses import dataclass

import httpx
from jinja2 import BaseLoader, Environment as JinjaEnv, TemplateError

from app.core.config import settings

log = logging.getLogger(__name__)

APP_URL = "https://conductai.ai"

_jinja = JinjaEnv(loader=BaseLoader(), autoescape=True)

# ---------------------------------------------------------------------------
# Hardcoded fallback templates (used if DB table not yet migrated)
# ---------------------------------------------------------------------------

_FALLBACK_TEMPLATES: dict[str, dict] = {
    "workspace_invite": {
        "subject": "You're invited to {{ workspace_name }} on Conduct AI",
        "html_body": """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8" /><title>Invited to {{ workspace_name }}</title></head>
<body style="margin:0;padding:0;background:#f5f5f4;font-family:-apple-system,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f4;padding:40px 0;">
    <tr><td align="center">
      <table width="560" cellpadding="0" cellspacing="0" style="max-width:560px;width:100%;">
        <tr><td align="center" style="padding-bottom:24px;">
          <span style="font-size:20px;font-weight:700;color:#1c1917;">Conduct AI</span>
        </td></tr>
        <tr><td style="background:#fff;border-radius:16px;border:1px solid #e7e5e4;padding:40px;">
          <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#1c1917;">
            You're invited to join<br/><span style="color:#4f46e5;">{{ workspace_name }}</span>
          </p>
          <p style="margin:0 0 24px;font-size:14px;color:#78716c;">
            {% if invited_by_email %}<b>{{ invited_by_email }}</b> has invited you{% else %}You've been invited{% endif %}
            to <b>{{ workspace_name }}</b> on Conduct AI.
          </p>
          <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
            <tr><td style="background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;">
              <p style="margin:0 0 2px;font-size:11px;font-weight:600;color:#15803d;text-transform:uppercase;">Your role</p>
              <p style="margin:0 0 4px;font-size:16px;font-weight:700;color:#1c1917;text-transform:capitalize;">{{ role }}</p>
              <p style="margin:0;font-size:12px;color:#57534e;">{{ role_description }}</p>
            </td></tr>
          </table>
          <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
            <tr><td style="background:#1c1917;border-radius:10px;">
              <a href="{{ app_url }}/sign-in"
                 style="display:inline-block;padding:14px 32px;font-size:15px;font-weight:600;color:#fff;text-decoration:none;">
                Accept invitation →
              </a>
            </td></tr>
          </table>
          <p style="margin:0;font-size:12px;color:#a8a29e;">
            Sign in with <b>this email address</b> and you'll be added to {{ workspace_name }} automatically.
          </p>
        </td></tr>
        <tr><td style="padding:16px 0;text-align:center;">
          <p style="margin:0;font-size:11px;color:#a8a29e;">
            Sent by Conduct AI · <a href="{{ app_url }}" style="color:#a8a29e;">{{ app_url }}</a><br/>
            If you weren't expecting this, you can safely ignore this email.
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>""",
    }
}

# ---------------------------------------------------------------------------
# Template loading + rendering
# ---------------------------------------------------------------------------

def render_template(slug: str, context: dict, db=None) -> tuple[str, str] | None:
    """
    Load template by slug from DB (preferred) or fallback dict.
    Returns (subject, html) with Jinja2 variables rendered, or None if slug unknown.
    """
    subject_tpl: str | None = None
    html_tpl: str | None = None

    if db is not None:
        try:
            from app.models.email_template import EmailTemplate
            row = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
            if row:
                subject_tpl = row.subject
                html_tpl = row.html_body
        except Exception as e:
            log.warning("Could not load email template '%s' from DB: %s", slug, e)

    if subject_tpl is None:
        fallback = _FALLBACK_TEMPLATES.get(slug)
        if not fallback:
            log.warning("Unknown email template slug: %s", slug)
            return None
        subject_tpl = fallback["subject"]
        html_tpl = fallback["html_body"]

    try:
        subject = _jinja.from_string(subject_tpl).render(**context)
        html = _jinja.from_string(html_tpl).render(**context)
        return subject, html
    except TemplateError as e:
        log.warning("Jinja2 render error for template '%s': %s", slug, e)
        return None


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sending
# ---------------------------------------------------------------------------

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
    """Send a pre-rendered email. Returns True on success."""
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


def send_template_email(
    *,
    slug: str,
    to: str,
    context: dict,
    workspace_id: str | None = None,
    db=None,
) -> bool:
    """Render template by slug and send. Returns True on success."""
    rendered = render_template(slug, context, db=db)
    if not rendered:
        return False
    subject, html = rendered
    return send_email(to=to, subject=subject, html=html, workspace_id=workspace_id, db=db)


# ---------------------------------------------------------------------------
# Convenience: invite_email_html kept for backward compat
# ---------------------------------------------------------------------------

_ROLE_DESCRIPTIONS = {
    "admin":  "Full access — manage members, credentials, environments, and agents.",
    "editor": "Run agents, edit workflows, and manage credentials.",
    "viewer": "Read-only access — view runs, workflows, and settings.",
}


def invite_email_html(*, workspace_name: str, invited_by_email: str | None, role: str) -> str:
    rendered = render_template("workspace_invite", {
        "workspace_name": workspace_name,
        "invited_by_email": invited_by_email or "",
        "role": role,
        "role_description": _ROLE_DESCRIPTIONS.get(role, ""),
        "app_url": APP_URL,
    })
    return rendered[1] if rendered else ""
