"""Customer-facing WARNING alert tests (#1520 PR 3).

The customer alerter now routes through the same
``guard_notification_channels`` fanout the workspace already uses for
block / warn / audit / approval. The old single-webhook path
(``GuardConfig.slack_webhook_url``) is no longer read from here.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.modules.guard.observability import customer_alert as ca


WS = "fd4b6608-f320-44b8-af22-fc579bd53600"


@pytest.fixture(autouse=True)
def _reset_state():
    ca._reset_dedup_for_tests()
    yield
    ca._reset_dedup_for_tests()


def _mk_db(notify_on_fail_open: bool = True):
    """Build a MagicMock db whose SELECT returns the opt-out row."""
    db = MagicMock()
    row = SimpleNamespace(notify_on_fail_open=notify_on_fail_open)
    db.execute.return_value.fetchone.return_value = row
    return db


def _mk_channel(channel_ref: str = "#security"):
    """One slack channel record — matches shape returned by resolve_channels."""
    return SimpleNamespace(
        id="ch-1",
        channel_type="slack",
        channel_ref=channel_ref,
        integration_id=None,
        enabled=True,
    )


# ── Happy path ──────────────────────────────────────────────────────────────

def test_fanout_called_when_channel_configured_and_opted_in():
    db = _mk_db()
    channels = [_mk_channel()]

    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=channels) as rc, \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout, \
         patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
        rwc.return_value = MagicMock(workspace_name="Acme Robotics", org_name=None)
        ca.notify_customer_fail_open(db, workspace_id=WS)

    rc.assert_called_once_with(db, WS, "fail_open")
    assert fanout.call_count == 1
    # _fanout_slack signature: (db, workspace_id, channels, text_msg)
    args = fanout.call_args.args
    assert args[1] == WS
    assert args[2] == channels
    text_msg = args[3]
    assert ":warning:" in text_msg
    assert "Acme Robotics" in text_msg
    assert "/theguard/settings" in text_msg


# ── Opt-out ──────────────────────────────────────────────────────────────

def test_skips_when_notify_on_fail_open_false():
    db = _mk_db(notify_on_fail_open=False)
    with patch("app.modules.guard.routers.notifications.resolve_channels") as rc, \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    # Never even resolves channels when opted out — cheap short-circuit
    assert rc.call_count == 0
    assert fanout.call_count == 0


def test_skips_when_no_channels_configured():
    db = _mk_db()
    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=[]), \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    assert fanout.call_count == 0


def test_none_db_is_safe():
    with patch("app.modules.guard.routers.events._fanout_slack") as fanout:
        ca.notify_customer_fail_open(None, workspace_id=WS)
    assert fanout.call_count == 0


# ── Rate limit ──────────────────────────────────────────────────────────────

def test_rate_limit_dedupes_within_15min_window():
    db = _mk_db()
    channels = [_mk_channel()]

    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=channels), \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout, \
         patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
        rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
        ca.notify_customer_fail_open(db, workspace_id=WS)
        ca.notify_customer_fail_open(db, workspace_id=WS)
        ca.notify_customer_fail_open(db, workspace_id=WS)

    assert fanout.call_count == 1


def test_burst_count_surfaces_after_window_flip(monkeypatch):
    monkeypatch.setattr(ca, "_RATE_LIMIT_SEC", 0)
    db = _mk_db()
    channels = [_mk_channel()]

    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=channels), \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout, \
         patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
        rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
        ca.notify_customer_fail_open(db, workspace_id=WS)
        ca.notify_customer_fail_open(db, workspace_id=WS)

    assert fanout.call_count == 2


# ── Defensive / never-raises ─────────────────────────────────────────────

def test_fanout_failure_does_not_raise():
    db = _mk_db()
    channels = [_mk_channel()]

    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=channels), \
         patch("app.modules.guard.routers.events._fanout_slack", side_effect=RuntimeError("slack down")), \
         patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
        rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
        # Must not raise
        ca.notify_customer_fail_open(db, workspace_id=WS)


def test_resolve_channels_failure_skips_silently():
    db = _mk_db()
    with patch("app.modules.guard.routers.notifications.resolve_channels", side_effect=RuntimeError("db down")), \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    assert fanout.call_count == 0


def test_config_lookup_failure_defaults_to_opted_in():
    """A DB error reading the opt-out flag must not silence transparency.
    The lookup treats an error as opted-in and continues to channel resolution."""
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")

    with patch("app.modules.guard.routers.notifications.resolve_channels", return_value=[]) as rc, \
         patch("app.modules.guard.routers.events._fanout_slack") as fanout:
        ca.notify_customer_fail_open(db, workspace_id=WS)

    # opt-in defaulted → still tried to resolve channels
    assert rc.call_count == 1
    # ... but no channels → no fanout
    assert fanout.call_count == 0


# ── Wire-through + message shape ─────────────────────────────────────────

def test_record_fail_open_wires_through_to_customer_notify():
    """One record_fail_open() call must delegate to the customer notify
    path (via _also_notify_customer). Spy pattern keeps the assertion
    deterministic and independent of the shared-httpx patch gotcha."""
    from app.modules.guard.observability import fail_open_alert as foa

    foa._reset_dedup_for_tests()
    ca._reset_dedup_for_tests()

    db = _mk_db()

    with patch("app.modules.guard.observability.fail_open_alert._also_notify_customer") as spy:
        foa.record_fail_open(db, workspace_id=WS, surface="proxy", error=RuntimeError("boom"))

    assert spy.call_count == 1
    called_db, called_ws = spy.call_args.args
    assert called_db is db
    assert called_ws == WS


def test_customer_message_omits_error_class_and_trace_id():
    """Audience-defining regression guard. The customer WARNING must
    never leak internal error details or a trace id — that's what makes
    it different from the internal ERROR alert."""
    text_msg = ca._build_message(workspace_name="Acme", count=3)

    assert ":warning:" in text_msg
    assert "Acme" in text_msg
    assert "3 requests" in text_msg
    assert "/theguard/settings" in text_msg
    assert "trace_id" not in text_msg
    assert "RuntimeError" not in text_msg
    assert "Exception" not in text_msg
