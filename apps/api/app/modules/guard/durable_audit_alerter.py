"""#1996 — Slack alerter for durable-audit failures.

The GUARD_AUDIT_FAILED Counter (app/modules/guard/observability/metrics.py)
already increments on every dropped write, but nothing is watching it —
if fail-closed 503s start firing in prod, the operator only finds out
from customer reports or by grepping logs.

This module snapshots the counter every N seconds, computes deltas,
and posts to Conduct's platform-operator Slack via the shared
``platform_slack.post_platform_alert`` helper when a per-reason threshold
is crossed. Two severities:

- ``reason="insert_accepted"`` delta > 0 in the last cycle → PAGE.
  The Gateway is serving 503s because the durable write failed. This
  is customer-impacting; someone needs to look now.
- ``reason="finalize"`` delta > threshold → WARN. Occasional finalize
  misses are OK (row lands orphaned, reconciler cleans it up); a
  sustained rate is not.

Per-alert cool-downs prevent Slack spam if the failure persists.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import structlog

from app.core.config import settings
from app.modules.guard.observability.platform_slack import post_platform_alert


log = structlog.get_logger(__name__)


# One state row per counter label so cool-downs are independent.
@dataclass
class _AlertState:
    last_value: float = 0.0
    # None = never alerted → cool-down check is a no-op. Using 0.0 here
    # would put the first-ever alert inside a false cool-down window
    # because ``now - 0`` is always << the 15-minute cool-down.
    last_alert_ts: float | None = None
    first_seen: bool = False


# Reason label → alert config
_ALERT_REASONS: dict[str, dict] = {
    "insert_accepted": {
        "severity": "PAGE",
        "threshold": 0.0,   # any increase is customer-impacting
        "headline": "Durable audit insert is failing — Gateway is serving 503s",
    },
    "finalize": {
        "severity": "WARN",
        "threshold": 5.0,   # up to 5 finalize misses per cycle is tolerable
        "headline": "Sustained durable-audit finalize failure rate",
    },
    "insert": {
        "severity": "WARN",
        "threshold": 0.0,
        "headline": "Legacy single-phase audit inserts are failing",
    },
    "renew_lease": {
        "severity": "WARN",
        "threshold": 5.0,
        "headline": "Sustained lease-renewal failures — reconciler may orphan live rows",
    },
    "late_finalize": {
        "severity": "WARN",
        "threshold": 0.0,
        "headline": "Late finalize on already-terminal row (indicates race with reconciler)",
    },
}


_state: dict[str, _AlertState] = {reason: _AlertState() for reason in _ALERT_REASONS}


def _counter_value(reason: str) -> float:
    """Read the current cumulative value of GUARD_AUDIT_FAILED for a label.

    prometheus_client keeps a ``_value`` object per label combination. We
    read it directly to avoid the cost of parsing the /metrics text
    format for one number.
    """
    try:
        from app.modules.guard.observability.metrics import GUARD_AUDIT_FAILED
        # ``labels`` returns a Counter child; ``._value.get()`` reads the
        # underlying atomic value.
        return float(GUARD_AUDIT_FAILED.labels(reason=reason)._value.get())
    except Exception:  # noqa: BLE001 — never let the alerter crash the loop
        return 0.0


def _post_slack(severity: str, reason: str, headline: str, delta: float, total: float) -> bool:
    """Delegate to the shared platform-alert helper.

    Kept as a thin function so the check-and-alert loop and the test
    suite have one patch point that decouples counter/state logic from
    the Slack transport.
    """
    text = f":rotating_light: [{severity}] Guard durable audit — {headline}"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*[{severity}] Guard durable audit alert*\n"
                    f"*Reason:* `{reason}`\n"
                    f"*Delta this cycle:* {delta:.0f}\n"
                    f"*Total since process start:* {total:.0f}\n"
                    f"\n"
                    f"{headline}\n"
                    f"\n"
                    f"_Runbook: docs/runbooks/durable-audit-insert-failing.md_"
                ),
            },
        }
    ]
    return post_platform_alert(surface="durable_audit", text=text, blocks=blocks)


def check_and_alert(now: float | None = None) -> dict[str, dict]:
    """One scan cycle. Returns a summary dict for tests / observability.

    First call after process start seeds the baseline without alerting
    (the counter's absolute value at startup is meaningless — only
    increases from now matter). Subsequent calls compute deltas.

    The cool-down (``guard_durable_audit_alerter_cooldown_seconds``)
    silences repeated pages for the same reason so a persistent failure
    doesn't flood Slack. The cool-down resets each time the failure
    stops firing.
    """
    now = now if now is not None else time.time()
    cooldown = settings.guard_durable_audit_alerter_cooldown_seconds
    summary: dict[str, dict] = {}

    for reason, cfg in _ALERT_REASONS.items():
        state = _state[reason]
        current = _counter_value(reason)

        if not state.first_seen:
            # First scan after process start — seed baseline, don't alert
            # on the accumulated value from a prior run's shared metric
            # backend (or, on a fresh start, from 0 → 0).
            state.last_value = current
            state.first_seen = True
            summary[reason] = {"delta": 0, "total": current, "action": "baseline"}
            continue

        delta = current - state.last_value
        state.last_value = current

        if delta <= cfg["threshold"]:
            summary[reason] = {"delta": delta, "total": current, "action": "quiet"}
            continue

        if state.last_alert_ts is not None and (now - state.last_alert_ts) < cooldown:
            summary[reason] = {
                "delta": delta,
                "total": current,
                "action": "cooldown",
                "cooldown_remaining": cooldown - (now - state.last_alert_ts),
            }
            continue

        sent = _post_slack(cfg["severity"], reason, cfg["headline"], delta, current)
        state.last_alert_ts = now
        summary[reason] = {
            "delta": delta,
            "total": current,
            "action": "alerted" if sent else "would_alert",
            "severity": cfg["severity"],
        }

    return summary


def durable_audit_alerter_loop() -> None:
    """Blocking loop for the worker process. Mirrors watchdog_loop shape.

    Uses time.sleep because both the counter and the worker are sync;
    an asyncio loop here would add complexity without benefit.
    """
    interval = settings.guard_durable_audit_alerter_seconds
    if interval <= 0:
        log.info("guard.durable_audit.alerter_disabled")
        return

    log.info("guard.durable_audit.alerter_started", interval_seconds=interval)
    while True:
        time.sleep(interval)
        try:
            check_and_alert()
        except Exception:
            log.exception("guard.durable_audit.alerter_error")


def _reset_state_for_tests() -> None:
    """Clears the module-level snapshot state. Test-only hook so a
    fresh alerter cycle can be simulated without process restart."""
    for reason in _ALERT_REASONS:
        _state[reason] = _AlertState()
