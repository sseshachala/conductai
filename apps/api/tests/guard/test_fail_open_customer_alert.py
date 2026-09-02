"""Customer-facing WARNING alert tests (#1520 PR 2).

Companion to test_fail_open_observability.py which covers the internal
ERROR alert. This file covers the customer WARNING path — different
audience, different framing, opt-out via guard_config.notify_on_fail_open,
15-min rate-limit per workspace.
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


def _mk_db(*, notify_on_fail_open: bool = True, slack_webhook_url: str | None = "https://hooks.slack.com/x/y/z"):
    db = MagicMock()
    row = SimpleNamespace(notify_on_fail_open=notify_on_fail_open, slack_webhook_url=slack_webhook_url)
    db.execute.return_value.fetchone.return_value = row
    return db


def test_posts_when_notify_on_and_webhook_set():
    db = _mk_db()
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme Robotics", org_name="Acme Inc.")
            ca.notify_customer_fail_open(db, workspace_id=WS)

    assert post.call_count == 1
    payload = post.call_args.kwargs["json"]
    # WARNING framing, no error class, no trace_id
    assert ":warning:" in payload["text"]
    assert "Acme Robotics" in payload["text"]
    assert "fail-open default" in payload["text"]
    # Settings link included
    assert "/theguard/settings" in payload["text"]
    # Never leak internal error details
    assert "RuntimeError" not in payload["text"]
    assert "trace_id" not in payload["text"]


def test_skips_when_notify_on_fail_open_false():
    db = _mk_db(notify_on_fail_open=False)
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    assert post.call_count == 0


def test_skips_when_webhook_url_empty():
    db = _mk_db(slack_webhook_url="")
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    assert post.call_count == 0


def test_skips_when_webhook_url_null():
    db = _mk_db(slack_webhook_url=None)
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(db, workspace_id=WS)
    assert post.call_count == 0


def test_rate_limit_dedupes_within_15min_window():
    db = _mk_db()
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            ca.notify_customer_fail_open(db, workspace_id=WS)
            ca.notify_customer_fail_open(db, workspace_id=WS)
            ca.notify_customer_fail_open(db, workspace_id=WS)

    # First post fires; next two silently deduped inside the 15-min window.
    assert post.call_count == 1


def test_burst_count_surfaces_after_window_flip(monkeypatch):
    monkeypatch.setattr(ca, "_RATE_LIMIT_SEC", 0)
    db = _mk_db()

    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            ca.notify_customer_fail_open(db, workspace_id=WS)
            ca.notify_customer_fail_open(db, workspace_id=WS)

    assert post.call_count == 2


def test_slack_post_failure_does_not_raise():
    db = _mk_db()
    with patch("app.modules.guard.observability.customer_alert.httpx.post", side_effect=RuntimeError("slack down")):
        with patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            # Must not raise — the caller has already fallen open.
            ca.notify_customer_fail_open(db, workspace_id=WS)


def test_db_lookup_failure_skips_silently():
    db = MagicMock()
    db.execute.side_effect = RuntimeError("db down")

    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(db, workspace_id=WS)

    # Config could not be loaded → no post, no raise.
    assert post.call_count == 0


def test_config_missing_row_skips_silently():
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = None

    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(db, workspace_id=WS)

    assert post.call_count == 0


def test_none_db_is_safe():
    with patch("app.modules.guard.observability.customer_alert.httpx.post") as post:
        ca.notify_customer_fail_open(None, workspace_id=WS)
    assert post.call_count == 0


def test_record_fail_open_end_to_end_fires_both_posts(monkeypatch):
    """Integrated wire-through: one record_fail_open() call must fire BOTH
    the internal ops alert AND the customer WARNING when both are configured
    (env var set + config row has slack_webhook_url + notify_on_fail_open=True).

    Gap-fill test — the isolated per-module tests stub the other side out;
    this one exercises the real record_fail_open path with a single httpx
    patch that captures every call, then partitions by webhook URL. That
    way the shared httpx module doesn't confuse per-module patches.
    """
    from app.modules.guard.observability import fail_open_alert as foa

    internal_webhook = "https://hooks.slack.com/internal/x/y"
    customer_webhook = "https://hooks.slack.com/x/y/z"  # matches _mk_db default

    monkeypatch.setenv(foa._ALERT_WEBHOOK_ENV, internal_webhook)
    foa._reset_dedup_for_tests()
    ca._reset_dedup_for_tests()

    db = _mk_db(slack_webhook_url=customer_webhook)

    with patch("httpx.post") as post, \
         patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc_i, \
         patch("app.modules.guard.observability.customer_alert.resolve_workspace_context") as rwc_c:
        rwc_i.return_value = MagicMock(workspace_name="Acme", org_name="Acme Inc.")
        rwc_c.return_value = MagicMock(workspace_name="Acme", org_name=None)

        foa.record_fail_open(db, workspace_id=WS, surface="proxy", error=RuntimeError("boom"))

    # Partition the two calls by which webhook URL they targeted.
    calls_by_url = {c.args[0]: c for c in post.call_args_list}
    assert internal_webhook in calls_by_url, "internal ops post did not fire"
    assert customer_webhook in calls_by_url, "customer WARNING post did not fire"
    assert len(post.call_args_list) == 2, f"expected exactly 2 posts, got {len(post.call_args_list)}"

    internal_text = calls_by_url[internal_webhook].kwargs["json"]["text"]
    customer_text = calls_by_url[customer_webhook].kwargs["json"]["text"]
    assert ":rotating_light:" in internal_text
    assert ":warning:" in customer_text
    assert "RuntimeError" in internal_text        # internal shows error class
    assert "RuntimeError" not in customer_text    # customer never sees it
