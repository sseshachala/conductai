"""
Output block executor.

Sends run results via Slack, email, or webhook.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import json

import structlog

log = structlog.get_logger(__name__)


def _execute_output(
    block: dict,
    state: dict,
    credentials: dict,
    workflow_name: str = "Agent",
    trace_url: str = "",
    run_id: str = "",
) -> dict:
    from app.runtime.integrations import slack, email as email_integration
    from app.core.config import settings
    from app.runtime.executor import (
        _build_run_summary,
        _fill_template,
        _load_template,
        _resolve_refs,
    )

    dry_run = state.get("__dry_run", False)
    data = block["data"]
    integration = data.get("integration", "slack")
    config = data.get("config", {})

    if dry_run:
        summary = _build_run_summary(state)
        return {"dry_run": True, "integration": integration, "preview": summary, "note": f"Dry run — would send via {integration}"}

    results: dict = {}

    send_slack = integration in ("slack", "both")
    send_email = integration in ("email", "both")

    if send_slack:
        slack_creds = credentials.get("slack", {})
        channel = _resolve_refs(config.get("channel", "#general"), state)
        if not slack_creds:
            results["slack"] = {"sent": False, "reason": "No Slack credentials configured"}
        elif not channel:
            results["slack"] = {"sent": False, "reason": "No Slack channel configured"}
        else:
            try:
                _, body = _fill_template(_load_template("slack_output.txt"), state, workflow_name, trace_url)
                use_approval = config.get("approval", False) and bool(run_id)
                if use_approval:
                    r = slack.execute("post_approval_message", {
                        "channel": channel,
                        "text": body,
                        "run_id": run_id,
                        "callback_url": trace_url,
                    }, slack_creds)
                else:
                    r = slack.execute("post_message", {"channel": channel, "text": body}, slack_creds)
                results["slack"] = r
            except Exception as e:
                results["slack"] = {"sent": False, "error": str(e)}

    if send_email:
        email_creds = dict(credentials.get("email", credentials.get("resend", {})))
        if not email_creds.get("resend_api_key") and settings.resend_api_key:
            email_creds["resend_api_key"] = settings.resend_api_key
        to = _resolve_refs(config.get("to", ""), state)
        from_address = config.get("from_address") or settings.email_from
        if not email_creds:
            results["email"] = {"sent": False, "reason": "No email credentials configured — add Resend or SendGrid in Settings"}
        elif not to:
            results["email"] = {"sent": False, "reason": "No recipient address configured — set 'Email address' on the output block"}
        else:
            try:
                subject, body = _fill_template(_load_template("email_output.txt"), state, workflow_name, trace_url)
                r = email_integration.execute("send_email", {"to": to, "subject": subject, "body": body, "from_address": from_address}, email_creds)
                results["email"] = r
            except Exception as e:
                results["email"] = {"sent": False, "error": str(e)}

    if integration == "webhook":
        import hashlib
        import hmac as hmac_lib
        import urllib.request
        webhook_url = _resolve_refs(config.get("webhook_url", ""), state)
        webhook_secret = config.get("webhook_secret", "")
        if not webhook_url:
            return {"sent": False, "reason": "No webhook URL configured"}
        payload = json.dumps({
            "workflow": workflow_name,
            "trace_url": trace_url,
            "state": {k: v for k, v in state.items() if not k.startswith("__")},
        }, default=str).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "ConductAI/1.0"}
        if webhook_secret:
            sig = hmac_lib.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
            headers["X-ConductAI-Signature"] = f"sha256={sig}"
        try:
            req = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"sent": True, "integration": "webhook", "status_code": resp.status}
        except Exception as e:
            return {"sent": False, "integration": "webhook", "error": str(e)}

    if not results:
        return {"sent": False, "reason": "No integration configured"}

    return {"sent": True, "integration": integration, **results}
