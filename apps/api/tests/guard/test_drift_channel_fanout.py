"""Drift alert routes through the per-action Slack fanout (#1574).

Before PR 4, the drift alert in savings.py called ``_send_guard_slack``
which reads the legacy single ``GuardConfig.alert_channel`` field. After
PR 4 the same alert routes via ``resolve_channels(db, ws, "drift")`` +
``_fanout_slack``, matching the pattern block/warn/audit/approval/
fail_open use.

These tests exercise the notifications layer directly rather than
running the full savings endpoint — savings integration coverage lives
in test_guard_savings.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.modules.guard.routers.notifications import ACTIONS


def test_drift_is_in_actions_tuple():
    """The new tier must be enumerated so POST/GET/DELETE endpoints accept it
    and the CHECK constraint on guard_notification_channels allows it."""
    assert "drift" in ACTIONS


def test_drift_action_matches_check_constraint_wording():
    """Regression guard: the CHECK constraint in migration 0112 must list
    exactly the same tiers as the ACTIONS tuple, otherwise inserts fail
    at DB level."""
    expected = {"block", "warn", "audit", "approval", "fail_open", "drift"}
    assert set(ACTIONS) == expected


def test_notification_create_accepts_drift_action():
    """The Pydantic Literal on ChannelCreate must allow 'drift' — if the
    Literal drifted from the ACTIONS tuple, this test catches it before
    the API returns 422 for anyone trying to add a drift channel."""
    from app.modules.guard.routers.notifications import ChannelCreate

    body = ChannelCreate(
        action="drift",
        channel_type="slack",
        channel_ref="#drift-alerts",
        integration_id=None,
    )
    assert body.action == "drift"


def test_post_slack_drift_is_removed():
    """The old webhook-URL helper is dead code — must not creep back in a
    revert. Explicit assertion so a rebase mistake surfaces immediately."""
    from app.modules.guard.routers import token_guardrails
    assert not hasattr(token_guardrails, "_post_slack_drift"), (
        "_post_slack_drift is dead code (had zero callers as of #1574). "
        "If it needs to come back, wire it in via resolve_channels+_fanout_slack "
        "instead of the legacy webhook URL."
    )


def test_guardconfig_no_longer_has_slack_webhook_url():
    """Column was dropped in migration 0112 (#1574). Model must not
    re-declare it or Alembic drift check will complain on next PR."""
    from app.modules.guard.models import GuardConfig
    assert not hasattr(GuardConfig, "slack_webhook_url"), (
        "GuardConfig.slack_webhook_url was dropped in migration 0112. "
        "Do not re-add — drift alerts route via resolve_channels('drift') now."
    )
