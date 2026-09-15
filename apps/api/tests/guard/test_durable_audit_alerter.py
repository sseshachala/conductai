"""#1996 — Slack alerter for durable-audit failures.

Locks the invariants the operator relies on when triaging a page:

- First cycle after process start is a baseline (never alerts).
- Zero delta = quiet (no alert, no log spam).
- Any insert_accepted delta > 0 fires (customer-impacting).
- finalize / renew_lease respect their thresholds.
- Cool-down silences a persistent failure so Slack doesn't flood.
- Missing token/channel = log-only (safe default in staging / local).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _fresh_alerter_state():
    """Every test starts with a clean baseline. The alerter's snapshot
    state is module-global (one process, one worker); tests must not
    share it with each other."""
    from app.modules.guard import durable_audit_alerter
    durable_audit_alerter._reset_state_for_tests()
    yield
    durable_audit_alerter._reset_state_for_tests()


def _set_counter(reason: str, value: float) -> None:
    """Force the counter to an absolute value for the test. We can't
    ``set`` a Counter (they're monotonic) so we increment the delta."""
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
    current = GUARD_AUDIT_FAILED.labels(reason=reason)._value.get()
    delta = value - current
    if delta > 0:
        GUARD_AUDIT_FAILED.labels(reason=reason).inc(delta)
    # A negative delta shouldn't happen — Counters only go up — but if
    # a prior test left the counter high we just skip; the test using
    # this shim will observe the delta from wherever the counter is.


def test_first_cycle_is_baseline_no_alert():
    """The counter's absolute value at process start is meaningless
    (a shared metrics backend or a prior test run could have left it
    non-zero). Only *increases from now* matter."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    _set_counter("insert_accepted", 42)

    summary = check_and_alert(now=100.0)

    assert summary["insert_accepted"]["action"] == "baseline"
    assert summary["insert_accepted"]["delta"] == 0


def test_zero_delta_is_quiet():
    """No new failures since last cycle → no alert, action=quiet."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    check_and_alert(now=100.0)  # baseline
    summary = check_and_alert(now=160.0)  # counter unchanged

    assert summary["insert_accepted"]["action"] == "quiet"
    assert summary["insert_accepted"]["delta"] == 0


def test_insert_accepted_delta_fires_on_any_increase():
    """The customer-impact reason has threshold 0 — even a single new
    fail-closed 503 pages."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED

    check_and_alert(now=100.0)  # baseline
    GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()

    with patch(
        "app.modules.guard.durable_audit_alerter._post_slack",
        return_value=True,
    ) as post:
        summary = check_and_alert(now=160.0)

    assert summary["insert_accepted"]["action"] == "alerted"
    assert summary["insert_accepted"]["severity"] == "PAGE"
    assert post.call_count == 1
    args, kwargs = post.call_args
    assert args[0] == "PAGE"
    assert args[1] == "insert_accepted"


def test_finalize_delta_respects_threshold():
    """A single finalize miss is expected under load — reconciler cleans
    it up. Only a sustained rate (threshold 5) should page."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED

    check_and_alert(now=100.0)  # baseline
    # Below threshold — should be quiet.
    GUARD_AUDIT_FAILED.labels(reason="finalize").inc(3)
    with patch("app.modules.guard.durable_audit_alerter._post_slack") as post_quiet:
        summary = check_and_alert(now=160.0)
    assert summary["finalize"]["action"] == "quiet"
    assert post_quiet.call_count == 0

    # Above threshold — should alert.
    GUARD_AUDIT_FAILED.labels(reason="finalize").inc(7)
    with patch(
        "app.modules.guard.durable_audit_alerter._post_slack",
        return_value=True,
    ) as post_alert:
        summary2 = check_and_alert(now=220.0)
    assert summary2["finalize"]["action"] == "alerted"
    assert post_alert.call_count == 1


def test_cooldown_suppresses_repeated_alerts():
    """A persistent failure keeps incrementing the counter every cycle.
    The alerter must page once, then stay silent for the cool-down
    window even if the delta keeps coming."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED

    check_and_alert(now=100.0)  # baseline

    # Cycle 1 — alert
    GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()
    with patch(
        "app.modules.guard.durable_audit_alerter._post_slack",
        return_value=True,
    ) as post:
        s1 = check_and_alert(now=160.0)
    assert s1["insert_accepted"]["action"] == "alerted"
    assert post.call_count == 1

    # Cycle 2 — still failing, only 60s later → cool-down
    GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()
    with patch(
        "app.modules.guard.durable_audit_alerter._post_slack",
        return_value=True,
    ) as post_cd:
        s2 = check_and_alert(now=220.0)
    assert s2["insert_accepted"]["action"] == "cooldown"
    assert post_cd.call_count == 0

    # Cycle 3 — past the cool-down window (default 15min = 900s) → alert again
    GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()
    with patch(
        "app.modules.guard.durable_audit_alerter._post_slack",
        return_value=True,
    ) as post_again:
        s3 = check_and_alert(now=160.0 + 1000)
    assert s3["insert_accepted"]["action"] == "alerted"
    assert post_again.call_count == 1


def test_missing_slack_config_falls_back_to_log_only():
    """Empty ``slack_bot_token`` or channel = alerter is safe to run
    everywhere (staging, local). It should still record ``would_alert``
    in the summary so tests + observability see the classification."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
    from app.core.config import settings

    _prev_token = settings.slack_bot_token
    _prev_channel = settings.conduct_internal_alert_slack_channel
    settings.slack_bot_token = ""
    settings.conduct_internal_alert_slack_channel = ""
    try:
        check_and_alert(now=100.0)  # baseline
        GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()
        summary = check_and_alert(now=160.0)
        assert summary["insert_accepted"]["action"] == "would_alert"
    finally:
        settings.slack_bot_token = _prev_token
        settings.conduct_internal_alert_slack_channel = _prev_channel


def test_slack_post_failure_does_not_crash_alerter():
    """Slack outage must never crash the alerter thread — the worker
    process would die and we'd lose the reconciler too."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
    from app.core.config import settings

    _prev_token = settings.slack_bot_token
    _prev_channel = settings.conduct_internal_alert_slack_channel
    settings.slack_bot_token = "xoxb-fake"
    settings.conduct_internal_alert_slack_channel = "#prod-alerts"

    try:
        check_and_alert(now=100.0)  # baseline
        GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()

        def _boom(*a, **kw):
            raise RuntimeError("Slack API returned 500")

        with patch("app.runtime.integrations.slack.post_message", _boom):
            summary = check_and_alert(now=160.0)

        # Not "alerted" because post failed, but the check completed.
        assert summary["insert_accepted"]["action"] == "would_alert"
    finally:
        settings.slack_bot_token = _prev_token
        settings.conduct_internal_alert_slack_channel = _prev_channel


def test_platform_slack_helper_called_with_surface_label():
    """When Slack config IS set, verify the durable-audit alerter routes
    through post_platform_alert with the ``durable_audit`` surface label
    so ops can grep which alerter fired."""
    from app.modules.guard.durable_audit_alerter import check_and_alert
    from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED

    check_and_alert(now=100.0)  # baseline
    GUARD_AUDIT_FAILED.labels(reason="insert_accepted").inc()

    with patch(
        "app.modules.guard.durable_audit_alerter.post_platform_alert",
        return_value=True,
    ) as helper:
        check_and_alert(now=160.0)

    assert helper.call_count == 1
    kwargs = helper.call_args.kwargs
    assert kwargs["surface"] == "durable_audit"
    assert "Guard durable audit" in kwargs["text"]
