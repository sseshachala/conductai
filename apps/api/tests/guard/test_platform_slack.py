"""Shared platform-operator Slack helper — the one place Conduct's
own health alerters (durable audit, and eventually fail-open + trial
spend) go through to post to the ops channel.

The contract this test locks:

- Missing bot token OR missing channel = log-only, returns False. Safe
  default in staging / local.
- Both set = post_message called with (token, channel, text, blocks).
- post_message raises = returned False, no exception propagates. The
  alerter thread must survive Slack outages.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _preserve_settings():
    """Restore settings after each test so we don't leak fake creds."""
    from app.core.config import settings
    _t = settings.slack_bot_token
    _c = settings.conduct_internal_alert_slack_channel
    yield
    settings.slack_bot_token = _t
    settings.conduct_internal_alert_slack_channel = _c


def _configure(token: str = "", channel: str = "") -> None:
    from app.core.config import settings
    settings.slack_bot_token = token
    settings.conduct_internal_alert_slack_channel = channel


def test_missing_token_is_log_only():
    from app.modules.guard.observability.platform_slack import post_platform_alert
    _configure(token="", channel="#prod-alerts")
    with patch("app.runtime.integrations.slack.post_message") as post:
        sent = post_platform_alert(surface="durable_audit", text="hi")
    assert sent is False
    assert post.call_count == 0


def test_missing_channel_is_log_only():
    from app.modules.guard.observability.platform_slack import post_platform_alert
    _configure(token="xoxb-fake", channel="")
    with patch("app.runtime.integrations.slack.post_message") as post:
        sent = post_platform_alert(surface="durable_audit", text="hi")
    assert sent is False
    assert post.call_count == 0


def test_both_set_posts_via_bot_api():
    from app.modules.guard.observability.platform_slack import post_platform_alert
    _configure(token="xoxb-fake", channel="#prod-alerts")
    with patch("app.runtime.integrations.slack.post_message") as post:
        sent = post_platform_alert(
            surface="durable_audit",
            text="test alert",
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": "hi"}}],
        )
    assert sent is True
    assert post.call_count == 1
    kwargs = post.call_args.kwargs
    assert kwargs["token"] == "xoxb-fake"
    assert kwargs["channel"] == "#prod-alerts"
    assert kwargs["text"] == "test alert"
    assert kwargs["blocks"] is not None


def test_post_message_failure_returns_false_and_does_not_raise():
    from app.modules.guard.observability.platform_slack import post_platform_alert
    _configure(token="xoxb-fake", channel="#prod-alerts")
    with patch(
        "app.runtime.integrations.slack.post_message",
        side_effect=RuntimeError("Slack API 500"),
    ):
        sent = post_platform_alert(surface="durable_audit", text="hi")
    assert sent is False  # never raises — alerter thread survives Slack outage
