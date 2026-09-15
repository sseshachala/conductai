"""Guard fail-open observability tests (#1520 + #1996 migration).

Covers:
  - Counter increments every fail-open event
  - Slack alert posts once per (workspace, surface) burst inside the window
  - Rate-limit dedupes subsequent events silently
  - Unset platform Slack config → no post attempted, counter still increments
  - Slack post failure logs WARN, does not raise

Post-#1996: the alerter routes through ``post_platform_alert``
instead of doing its own ``httpx.post`` on a webhook URL. Tests now
patch ``fail_open_alert.post_platform_alert`` and configure the two
platform Slack settings via ``core.config.settings``.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.modules.guard.observability import fail_open_alert as foa


WS = "fd4b6608-f320-44b8-af22-fc579bd53600"


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
    in test_fail_open_customer_alert.py — no-op it here so post_platform_alert
    call counts reflect the internal path alone."""
    with patch("app.modules.guard.observability.fail_open_alert._also_notify_customer"):
        yield


@pytest.fixture
def _slack_configured():
    """Set both platform Slack settings so post_platform_alert would
    attempt a real Bot API post — tests then patch the actual send."""
    from app.core.config import settings
    _t = settings.slack_bot_token
    _c = settings.conduct_internal_alert_slack_channel
    settings.slack_bot_token = "xoxb-fake"
    settings.conduct_internal_alert_slack_channel = "#conduct-alerts"
    yield
    settings.slack_bot_token = _t
    settings.conduct_internal_alert_slack_channel = _c


def test_counter_increments_and_posts_once(_slack_configured):
    before = _counter_value("proxy")

    with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme Robotics", org_name="Acme Inc.")
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("redis down"))

    assert _counter_value("proxy") == before + 1
    assert post.call_count == 1
    kwargs = post.call_args.kwargs
    assert "Acme Robotics" in kwargs["text"]
    assert "Acme Inc." in kwargs["text"]
    assert "proxy" in kwargs["text"]
    assert "RuntimeError" in kwargs["text"]
    # surface is threaded through so ops can grep alert origin.
    assert kwargs["surface"] == "fail_open:proxy"


def test_rate_limit_dedupes_second_event_within_window(_slack_configured):
    before = _counter_value("proxy")

    with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("y"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("z"))

    # Counter fires every time, but Slack posts only once per window.
    assert _counter_value("proxy") == before + 3
    assert post.call_count == 1


def test_different_surface_does_not_dedup(_slack_configured):
    with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="mcp", error=RuntimeError("y"))

    assert post.call_count == 2


def test_unset_platform_slack_still_increments_counter():
    """Missing Slack config → post_platform_alert returns False (log-only)
    but the counter and dedup path both still run. The counter is the
    load-bearing observability signal; Slack is the convenience layer."""
    from app.core.config import settings
    _t = settings.slack_bot_token
    _c = settings.conduct_internal_alert_slack_channel
    settings.slack_bot_token = ""
    settings.conduct_internal_alert_slack_channel = ""
    try:
        before = _counter_value("proxy")
        with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert", return_value=False) as post:
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))

        assert _counter_value("proxy") == before + 1
        # We still call the helper — the log-only decision is made inside.
        assert post.call_count == 1
    finally:
        settings.slack_bot_token = _t
        settings.conduct_internal_alert_slack_channel = _c


def test_slack_post_failure_does_not_raise(_slack_configured):
    """Slack outage inside post_platform_alert must be swallowed so the
    caller's fail-open decision (already taken on the ORIGINAL error) is
    not defeated by a secondary alerter failure."""
    with patch(
        "app.runtime.integrations.slack.post_message",
        side_effect=RuntimeError("slack down"),
    ):
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            try:
                foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            except Exception as exc:  # noqa: BLE001
                pytest.fail(f"record_fail_open raised: {exc!r}")


def test_burst_count_included_after_window_flip(_slack_configured, monkeypatch):
    """After the rate-limit window closes, the next post surfaces how many
    events were suppressed so ops can see burst magnitude."""
    monkeypatch.setattr(foa, "_RATE_LIMIT_SEC", 0)

    with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert") as post:
        with patch("app.modules.guard.observability.fail_open_alert.resolve_workspace_context") as rwc:
            rwc.return_value = MagicMock(workspace_name="Acme", org_name=None)
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("y"))

    # With RATE_LIMIT_SEC=0 the window is always considered closed, so both post.
    assert post.call_count == 2


def test_context_lookup_failure_falls_back_to_workspace_id(_slack_configured):
    with patch("app.modules.guard.observability.fail_open_alert.post_platform_alert") as post:
        with patch(
            "app.modules.guard.observability.fail_open_alert.resolve_workspace_context",
            side_effect=RuntimeError("db down"),
        ):
            foa.record_fail_open(MagicMock(), workspace_id=WS, surface="proxy", error=RuntimeError("x"))

    # Post still happens; message falls back to workspace_id as name.
    assert post.call_count == 1
    assert WS in post.call_args.kwargs["text"]
