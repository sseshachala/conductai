"""
Approval block executor.

Pauses the run and sends Slack/email approval request.
Extracted from app.runtime.executor.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


def _execute_approval(block: dict, state: dict, credentials: dict, run_id: str) -> dict:
    """
    Pause the run and send a Slack DM with Approve/Reject buttons.
    Raises ApprovalRequired so the executor can pause the run.

    On resume, the executor injects __approval_{block_id} = 'approved'|'rejected'
    into state before re-queuing, so the block returns without raising.
    """
    from app.runtime.integrations import slack
    from app.core.config import settings
    from app.runtime.executor import ApprovalRequired, _resolve_refs

    block_id = block["id"]
    approval_key = f"__approval_{block_id}"

    # Resuming — decision already recorded by the approval webhook
    if approval_key in state:
        decision = state[approval_key]
        if decision == "rejected":
            raise ValueError(f"Approval rejected for block {block_id}")
        return {"decision": "approved", "resumed": True}

    # First encounter — send Slack/email/both notification and pause
    data = block["data"]
    config = data.get("config", {})
    message = _resolve_refs(
        config.get("message", data.get("description", "Approval required to continue.")),
        state,
    )
    via = config.get("via", "slack")
    slack_user = config.get("slack_user")
    channel = config.get("channel", "#general")
    approval_email = config.get("approval_email")
    callback_url = f"{settings.api_base_url}/runs/{run_id}/approve"

    # ── Slack ──────────────────────────────────────────────────────────────────
    if via in ("slack", "both"):
        slack_creds = credentials.get("slack", {})
        if slack_creds:
            try:
                slack.execute(
                    "post_approval_message",
                    {
                        "channel": slack_user or channel,
                        "text": message,
                        "run_id": run_id,
                        "callback_url": callback_url,
                    },
                    slack_creds,
                )
            except Exception as e:
                log.warning("approval.slack_failed", error=str(e))

    # ── Email ──────────────────────────────────────────────────────────────────
    if via in ("email", "both") and approval_email:
        try:
            from app.runtime.integrations import email as email_int
            approve_url = f"{callback_url}?run_id={run_id}&decision=approved"
            reject_url  = f"{callback_url}?run_id={run_id}&decision=rejected"
            email_body = (
                f"{message}\n\n"
                f"Approve: {approve_url}\n"
                f"Reject:  {reject_url}\n"
            )
            email_creds = credentials.get("email", credentials.get("resend", {}))
            email_int.execute(
                "send",
                {
                    "to": approval_email,
                    "subject": f"Approval required — run {run_id[:8]}",
                    "body": email_body,
                },
                email_creds,
            )
        except Exception as e:
            log.warning("approval.email_failed", error=str(e))

    raise ApprovalRequired(block_id, message)
