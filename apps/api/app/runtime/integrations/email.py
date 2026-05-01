"""
Email integration — supports Resend and SendGrid.
Actions: send_email.
"""
import httpx


def send_via_resend(api_key: str, to: str, subject: str, body: str, from_address: str = "Delegator <notifications@delegator.dev>") -> dict:
    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"from": from_address, "to": [to], "subject": subject, "text": body},
        timeout=15,
    )
    r.raise_for_status()
    d = r.json()
    return {"sent": True, "provider": "resend", "id": d.get("id"), "to": to, "subject": subject}


def send_via_sendgrid(api_key: str, to: str, subject: str, body: str, from_address: str = "notifications@delegator.dev") -> dict:
    r = httpx.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": from_address},
            "subject": subject,
            "content": [{"type": "text/plain", "value": body}],
        },
        timeout=15,
    )
    r.raise_for_status()
    return {"sent": True, "provider": "sendgrid", "to": to, "subject": subject}


def send_email(credentials: dict, to: str, subject: str, body: str, from_address: str | None = None) -> dict:
    kwargs: dict = {"to": to, "subject": subject, "body": body}
    if from_address:
        kwargs["from_address"] = from_address

    if credentials.get("resend_api_key"):
        return send_via_resend(api_key=credentials["resend_api_key"], **kwargs)
    if credentials.get("sendgrid_api_key"):
        return send_via_sendgrid(api_key=credentials["sendgrid_api_key"], **kwargs)

    raise ValueError("No email credentials configured — add a Resend or SendGrid API key in Settings")


TOOL_MAP = {"send_email": send_email}


def execute(action: str, params: dict, credentials: dict) -> dict:
    fn = TOOL_MAP.get(action)
    if not fn:
        raise ValueError(f"Unknown email action: {action}")
    return fn(credentials=credentials, **params)
