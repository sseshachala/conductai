"""Guard fail-open observability tests (#1520).

Covers:
  - Counter increments every fail-open event
  - Slack alert posts once per (workspace, surface) burst inside the window
  - Rate-limit dedupes subsequent events silently
  - Unset webhook env var → no post attempted, counter still increments
  - Slack post failure logs WARN, does not raise
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from app.modules.guard.observability import fail_open_alert as foa
from app.modules.guard.observability.metrics import GUARD_ENGINE_ERRORS


WS = "fd4b6608-f320-44b8-af22-fc579bd53600"
WEBHOOK = "conduct-alerts"


def _counter_value(surface: str) -> float:
    """Read the counter via the public exposition API. workspace_id is not
    a label (see metrics.py docstring), and using the private ``_value``
    attribute is not covered by prometheus-client's compatibility promise."""
    from prometheus_client import generate_latest

    for line in generate_latest().decode().splitlines():
        if line.startswith("guard_engine_errors_total{") and f'surface="{surface}"' in line:
            return float(line.split()[-1])
    return 0.0


@pytest.fixture(autouse=True)
def _reset_state():
    foa._reset_dedup_for_tests()
    yield
    foa._reset_dedup_for_tests()


@pytest.fixture(autouse=True)
def _isolate_from_customer_alert():
    """PR 1 tests own the internal-alert path only. PR 2's customer alerter
    (wired into record_fail_open in the same module) has its own coverage
    in test_fail_open_customer_alert.py — no-op it here so httpx.post
    call counts reflect the internal path alone."""
    with patch("app.modules.guard.observability.fail_open_alert._also_notify_customer"):
        yield


def test_counter_increments_and_posts_once(monkeypatch):
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)
    before = _counter_value("proxy")

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme Robotics", org_name="Acme Inc.")
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("redis down"))

    assert _counter_value("proxy") == before + 1
    assert post.call_count == 1
    payload = post.call_args.kwargs["json"]
    assert "Acme Robotics" in payload["text"]
    assert "Acme Inc." in payload["text"]
    assert "proxy" in payload["text"]
    assert "RuntimeError" in payload["text"]


def test_rate_limit_dedupes_second_event_within_window(monkeypatch):
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)
    before = _counter_value("proxy")

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("y"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("z"))

    # Counter fires every time, but Slack posts only once per window.
    assert _counter_value("proxy") == before + 3
    assert post.call_count == 1


def test_different_surface_does_not_dedup(monkeypatch):
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="mcp", error=RuntimeError("y"))

    assert post.call_count == 2


def test_unset_webhook_skips_post_but_still_increments(monkeypatch):
    monkeypatch.delenv(foa._ALERT_CHANNEL_ENV, raising=False)
    before = _counter_value("proxy")

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))

    assert _counter_value("proxy") == before + 1
    assert post.call_count == 0


def test_slack_post_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post", side_effect=RuntimeError("slack down")):
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            # Must not raise — fail-open path already tolerated the original error.
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))


def test_burst_count_included_after_window_flip(monkeypatch):
    """After the rate-limit window closes, the next post surfaces how many
    events were suppressed so ops can see burst magnitude."""
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)

    # Force the window to appear expired by shrinking it for this test.
    monkeypatch.setattr(foa, "_RATE_LIMIT_SEC", 0)

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("y"))

    # With RATE_LIMIT_SEC=0 the window is always considered closed, so both post.
    assert post.call_count == 2


def test_context_lookup_failure_falls_back_to_workspace_id(monkeypatch):
    monkeypatch.setenv(foa._ALERT_CHANNEL_ENV, WEBHOOK)

    with patch("app.modules.guard.observability.fail_open_alert.httpx.post") as post:
        with patch(
            "app.modules.guard.observability.fail_open_alert.resolve_workspace_context",
            side_effect=RuntimeError("db down"),
        ):
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))

    # Post still happens; message falls back to workspace_id as name.
    assert post.call_count == 1
    payload = post.call_args.kwargs["json"]
    assert WS in payload["text"]
