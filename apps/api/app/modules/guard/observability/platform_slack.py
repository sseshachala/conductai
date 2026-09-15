"""Shared Slack post for Conduct's platform-operator alerts.

Two distinct alert channels exist in the codebase:

- **Platform-operator alerts** (this module) go to CONDUCT'S OWN Slack
  workspace. Used when Conduct's own systems are broken — durable audit
  failing, engine falling open across all workspaces, trial spend runaway.
  Audience is Sudhi + the Conduct team.
- **Workspace-owner alerts** go to the CUSTOMER'S Slack workspace via
  their own credential in the vault + their Notifications-page channel
  choice. Used for events inside that specific workspace — Block, Warn,
  Audit, Approval, Fail-open (customer heads-up), Drift.

Both eventually hit the same ``app.runtime.integrations.slack.post_message``
Bot-API call. What differs is the (token, channel) pair — platform alerts
pull them from Render env vars; workspace alerts pull them per-workspace.

This module is the one place platform alerters call. Bot token + channel
both live in ``app.core.config.settings``; if either is empty the post is
a log-only no-op (safe default for staging / local).

Legacy webhook path: ``fail_open_alert.py`` and ``trial_spend_alert.py``
still use ``CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL`` as a webhook URL. They
will be migrated onto this helper as a follow-up so all three internal
alerters share one credential path.
"""
from __future__ import annotations

import structlog

from app.core.config import settings


log = structlog.get_logger(__name__)


def post_platform_alert(
    *,
    surface: str,
    text: str,
    blocks: list | None = None,
) -> bool:
    """Post a single platform-operator alert. Returns True if sent.

    ``surface`` is a short label (e.g. ``"durable_audit"``) that goes
    into the structlog line so operators can grep which alerter fired.
    It is NOT sent to Slack — the Slack message content lives in
    ``text`` / ``blocks``.

    Contract:
    - Both ``slack_bot_token`` and ``conduct_internal_alert_slack_channel``
      set → attempt post via Bot API. Returns True on success.
    - Either missing → log-only. Returns False.
    - Slack post raises → swallow + log warning + return False. Never
      let the alerter thread die and take the reconciler down with it.
    """
    token = settings.slack_bot_token
    channel = settings.conduct_internal_alert_slack_channel
    if not token or not channel:
        log.info(
            "platform.alert_would_fire",
            surface=surface,
            note="SLACK_BOT_TOKEN or CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL not set — log only",
        )
        return False

    try:
        from app.runtime.integrations.slack import post_message
        post_message(token=token, channel=channel, text=text, blocks=blocks)
        log.info("platform.alert_sent", surface=surface)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("platform.alert_slack_failed", surface=surface, err=str(exc))
        return False
