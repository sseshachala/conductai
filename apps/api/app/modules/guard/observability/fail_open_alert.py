"""Internal Slack alerter for Guard fail-open events (#1520).

Posts a single Slack message per (workspace_id, surface) burst so a broken
policy engine (e.g. Redis outage) can't spam the ops channel thousands of
times per minute. Reads ``CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL`` from env;
if unset the alerter no-ops and only the Prometheus counter fires.

Customer-facing WARNING alerts (using the workspace's own Slack config) are
tracked separately in PR 2 of #1520.
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
import structlog
from sqlalchemy.orm import Session

from app.modules.guard.observability.metrics import GUARD_ENGINE_ERRORS
from app.modules.guard.observability.name_cache import resolve_workspace_context

log = structlog.get_logger(__name__)

_ALERT_CHANNEL_ENV = "CONDUCT_INTERNAL_ALERT_SLACK_CHANNEL"
_RATE_LIMIT_SEC = 300  # 5 minutes per (workspace_id, surface)
_HTTP_TIMEOUT_SEC = 3.0

# In-process dedup: (workspace_id, surface) -> (first_hit_monotonic, burst_count)
_dedup: dict[tuple[str, str], tuple[float, int]] = {}


def _now() -> float:
    return time.monotonic()


def _should_post(key: tuple[str, str]) -> tuple[bool, int]:
    """Decide whether to emit for this (workspace, surface) key.

    Returns (post_now, burst_count). The first hit posts immediately with
    burst=1; subsequent hits inside the window increment the burst counter
    silently. When the window closes, the next hit posts again with the
    accumulated burst count from the prior window (so the ops channel
    still sees magnitude).
    """
    now = _now()
    prior = _dedup.get(key)
    if prior is None:
        _dedup[key] = (now, 1)
        return True, 1

    first_hit, burst = prior
    if now - first_hit < _RATE_LIMIT_SEC:
        _dedup[key] = (first_hit, burst + 1)
        return False, burst + 1

    _dedup[key] = (now, 1)
    return True, burst  # burst from the prior window, included for context


def _build_message(
    *,
    workspace_id: str,
    workspace_name: str,
    org_name: str | None,
    surface: str,
    error: BaseException,
    burst: int,
) -> dict:
    org_line = f"*Org:* {org_name}\n" if org_name else ""
    burst_line = f"\n*Burst:* {burst} events in the last window" if burst > 1 else ""
    return {
        "text": (
            f":rotating_light: *Guard fail-open* — engine errored, requests allowed through\n"
            f"*Workspace:* {workspace_name} (`{workspace_id}`)\n"
            f"{org_line}"
            f"*Surface:* `{surface}`\n"
            f"*Error:* `{type(error).__name__}: {str(error)[:200]}`"
            f"{burst_line}"
        ),
    }


def record_fail_open(
    db: Session | None,
    *,
    workspace_id: str | uuid.UUID,
    surface: str,
    error: BaseException,
) -> None:
    """Single call-site for every fail-open except: block.

    Always increments the Prometheus counter. Best-effort Slack post to
    Conduct's internal ops channel, rate-limited per (workspace, surface).
    Never raises — the caller has already decided to fall open on the
    original error and any exception here would defeat that decision.
    """
    ws_id = str(workspace_id)
    try:
        # workspace_id intentionally NOT a label — see metrics.py module
        # docstring. Workspace context lives in the Slack post + structlog
        # line just below.
        from app.core.config import settings as _settings
        GUARD_ENGINE_ERRORS.labels(
            surface=surface,
            env=getattr(_settings, "environment", "unknown"),
        ).inc()
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.counter_failed", err=str(exc))

    # Customer WARNING fires alongside the internal ERROR — different
    # audiences, different framing (#1520 PR 2). Rate-limited independently
    # in customer_alert._should_post.
    _also_notify_customer(db, ws_id)

    webhook = os.environ.get(_ALERT_CHANNEL_ENV, "").strip()
    if not webhook:
        return

    post_now, burst = _should_post((ws_id, surface))
    if not post_now:
        return

    if db is not None:
        try:
            ctx = resolve_workspace_context(db, ws_id)
        except Exception as exc:  # noqa: BLE001 — never raise from alert path
            log.warning("guard.fail_open.context_lookup_failed", err=str(exc))
            ctx = None
    else:
        ctx = None

    workspace_name = ctx.workspace_name if ctx else ws_id
    org_name = ctx.org_name if ctx else None
    payload = _build_message(
        workspace_id=ws_id,
        workspace_name=workspace_name,
        org_name=org_name,
        surface=surface,
        error=error,
        burst=burst,
    )

    try:
        httpx.post(webhook, json=payload, timeout=_HTTP_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001
        # Slack itself failed. Log at WARN; do not retry — the outage that
        # triggered fail-open may also be affecting outbound network.
        log.warning("guard.fail_open.slack_post_failed", err=str(exc), surface=surface)


def _also_notify_customer(db: Session | None, workspace_id: str) -> None:
    """Split out so record_fail_open() has one clean control-flow path.
    Customer notification is best-effort and never raises."""
    from app.modules.guard.observability.customer_alert import notify_customer_fail_open
    try:
        notify_customer_fail_open(db, workspace_id=workspace_id)
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_notify_failed", err=str(exc))


def _reset_dedup_for_tests() -> None:
    _dedup.clear()
