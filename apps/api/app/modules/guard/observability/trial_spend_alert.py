"""Internal Slack alert on aggregate trial-key spend crossing threshold (#1587 A3).

Fires from the trial-key resolver (`trial_upstream.resolve_trial_key`) when
a trial call is served. Reuses the same webhook + rate-limit shape as the
fail-open alerter (`fail_open_alert.py`) — one internal ops channel, one
env var, no reinvention.

Env config:
  CONDUCT_INTERNAL_ALERT_SLACK_WEBHOOK  — reused; unset = no-op (silent).
  GUARD_TRIAL_DAILY_ALERT_USD           — threshold; unset = no-op.

Rate limit: one post per hour. Threshold is a "soft" alert — once it
fires, don't re-fire until spend keeps rising past the last-alerted level.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

import httpx
import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.modules.guard.trial_seed import TRIAL_IDENTITY_NAME

log = structlog.get_logger(__name__)

_ALERT_WEBHOOK_ENV = "CONDUCT_INTERNAL_ALERT_SLACK_WEBHOOK"
_THRESHOLD_ENV = "GUARD_TRIAL_DAILY_ALERT_USD"
_RATE_LIMIT_SEC = 3600  # one alert per hour
_HTTP_TIMEOUT_SEC = 3.0

# In-process dedup: (posix-day,) -> (last_post_monotonic, last_spend_alerted)
# Keyed by day so the counter resets naturally at UTC midnight.
_dedup: dict[str, tuple[float, float]] = {}


def _now() -> float:
    return time.monotonic()


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _within_rate_limit() -> bool:
    """Cheap pure-timestamp check — used to short-circuit before the SQL
    query when we know we can't post yet."""
    prior = _dedup.get(_today_key())
    return prior is not None and _now() - prior[0] < _RATE_LIMIT_SEC


def _should_post(spend_usd: float) -> tuple[bool, float]:
    """Return (post_now, last_spend_alerted).

    Post iff:
      - never posted today, OR
      - past the rate-limit window AND spend has grown at least 25% beyond
        the last alerted value. Prevents re-alerting on the same $X noise
        every hour when spend has plateaued.
    """
    prior = _dedup.get(_today_key())
    if prior is None:
        return True, 0.0
    last_post, last_alerted = prior
    if _now() - last_post < _RATE_LIMIT_SEC:
        return False, last_alerted
    if spend_usd < last_alerted * 1.25:
        return False, last_alerted
    return True, last_alerted


def _record_posted(spend_usd: float) -> None:
    _dedup[_today_key()] = (_now(), spend_usd)


def _get_spend_today(db: Session) -> float:
    """SUM(cost_usd_after) for trial-identity audit rows in the last 24h."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    return float(
        db.execute(
            text("""
                SELECT COALESCE(SUM(ae.cost_usd_after), 0)
                FROM guard_audit_events ae
                JOIN agent_identities ai ON ai.id = ae.agent_identity_id
                WHERE ai.name = :name AND ae.ts >= :cutoff
            """),
            {"name": TRIAL_IDENTITY_NAME, "cutoff": cutoff},
        ).scalar() or 0.0
    )


def _build_message(*, spend_usd: float, threshold_usd: float, last_alerted: float) -> dict:
    growth_line = (
        f"\n*Growth since last alert:* +${spend_usd - last_alerted:.2f} "
        f"(previous alert at ${last_alerted:.2f})"
        if last_alerted > 0 else ""
    )
    return {
        "text": (
            f":money_with_wings: *Trial spend crossed threshold*\n"
            f"*Today's spend:* ${spend_usd:.2f}\n"
            f"*Alert threshold:* ${threshold_usd:.2f}"
            f"{growth_line}\n"
            f"See `/guard/trial/ops` for the top-10 workspaces."
        ),
    }


def check_and_alert_trial_spend(db: Session) -> None:
    """Query today's trial spend and post to the internal ops channel if
    it exceeds the threshold. Never raises — the trial-key resolver has
    already decided to serve the key and any exception here must not
    defeat that decision.
    """
    try:
        webhook = os.environ.get(_ALERT_WEBHOOK_ENV, "").strip()
        threshold_raw = os.environ.get(_THRESHOLD_ENV, "").strip()
        if not webhook or not threshold_raw:
            return
        try:
            threshold = float(threshold_raw)
        except ValueError:
            log.warning("guard.trial.spend_alert.bad_threshold", value=threshold_raw)
            return

        # Short-circuit before the SQL query when we know we can't post.
        # Every trial call runs `resolve_trial_key`, so this dedup gate
        # matters for perf, not just Slack spam.
        if _within_rate_limit():
            return

        spend = _get_spend_today(db)
        if spend < threshold:
            return

        post_now, last_alerted = _should_post(spend)
        if not post_now:
            return

        payload = _build_message(
            spend_usd=spend, threshold_usd=threshold, last_alerted=last_alerted,
        )
        try:
            httpx.post(webhook, json=payload, timeout=_HTTP_TIMEOUT_SEC)
            _record_posted(spend)
            log.info("guard.trial.spend_alert.posted", spend_usd=spend, threshold_usd=threshold)
        except Exception as exc:  # noqa: BLE001
            log.warning("guard.trial.spend_alert.slack_post_failed", err=str(exc))
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.trial.spend_alert.unhandled", err=str(exc))


def _reset_dedup_for_tests() -> None:
    _dedup.clear()
