"""Alert source / event registry (#2142, #2524).

One place that says which alertable sources exist and which event types each
can raise. The unified Guard > Connections > Notifications page renders from
``GET /guard/alerts/registry``, so a new source only needs a ``register_source``
call (here or at import time in its own module) -- no UI change.

Channel rows live in ``guard_notification_channels``:
  * Guard rules keep ``source_type='guard'`` and use ``action`` as the event
    (unchanged behaviour).
  * Every other source stores ``action='alert'`` plus ``source_type``,
    ``event_type`` and optional ``source_id`` (NULL = all instances).
"""
from __future__ import annotations

from dataclasses import dataclass, field

GUARD_SOURCE = "guard"
ALERT_ACTION = "alert"  # value of `action` for every non-guard row

SEVERITIES = ("info", "warning", "error", "critical")


@dataclass(frozen=True)
class EventDef:
    event_type: str
    label: str
    description: str = ""
    severity: str = "warning"
    # Per-channel "only alert at >= N events per minute" threshold supported.
    supports_threshold: bool = False
    default_dedupe_sec: int = 300


@dataclass(frozen=True)
class SourceDef:
    source_type: str
    label: str
    # True when rows may target one instance (e.g. a gateway profile id).
    scoped: bool = False
    events: tuple[EventDef, ...] = field(default_factory=tuple)

    def event(self, event_type: str) -> EventDef | None:
        return next((e for e in self.events if e.event_type == event_type), None)


_REGISTRY: dict[str, SourceDef] = {}


def register_source(source: SourceDef) -> None:
    """Register (or replace) a source. Idempotent."""
    for ev in source.events:
        if ev.severity not in SEVERITIES:
            raise ValueError(f"{source.source_type}.{ev.event_type}: bad severity {ev.severity!r}")
    _REGISTRY[source.source_type] = source


def get_source(source_type: str) -> SourceDef | None:
    return _REGISTRY.get(source_type)


def get_event(source_type: str, event_type: str) -> EventDef | None:
    src = _REGISTRY.get(source_type)
    return src.event(event_type) if src else None


def list_sources() -> list[SourceDef]:
    return list(_REGISTRY.values())


# ── Built-in sources ─────────────────────────────────────────────────────────

# Guard rules: events are the legacy action tiers. Listed for the table view
# only; their fan-out stays in routers/events_notify.py and is unchanged.
register_source(SourceDef(
    source_type=GUARD_SOURCE,
    label="Guard rules",
    events=(
        EventDef("block", "Blocked", severity="error"),
        EventDef("warn", "Warned", severity="warning"),
        EventDef("audit", "Audited", severity="info"),
        EventDef("approval", "Approval requested", severity="error"),
        EventDef("fail_open", "Fail-open", severity="warning"),
        EventDef("drift", "Drift", severity="warning"),
    ),
))

register_source(SourceDef(
    source_type="gateway",
    label="Gateway profile",
    scoped=True,
    events=(
        EventDef("admission_refused", "Admission refused (429)",
                 "Request refused at admission.", "warning", True, 300),
        EventDef("spend_cap_refused", "Spend cap refused (503)",
                 "Request refused because a spend cap was reached.", "error", True, 300),
        EventDef("upstream_5xx", "Upstream 5xx",
                 "Upstream provider returned a 5xx.", "error", True, 300),
        EventDef("upstream_timeout", "Upstream timeout",
                 "Upstream provider timed out.", "warning", True, 300),
        EventDef("rate_limit_exceeded", "Rate limit exceeded",
                 "Profile rate limit exceeded.", "warning", True, 300),
    ),
))

register_source(SourceDef(
    source_type="audit_feed",
    label="Audit feed",
    events=(
        EventDef("collector_stale", "Collector stale",
                 "A SIEM collector stopped pulling (fires on stale and on recovery).",
                 "error", False, 0),
    ),
))

# TODO(#2524): nothing raises this yet. Chain verification is on-demand only
# (routers/verify.py); call dispatch_alert("audit_chain", "verification_failed")
# once a scheduled verification exists.
register_source(SourceDef(
    source_type="audit_chain",
    label="Audit chain",
    events=(
        EventDef("verification_failed", "Verification failed",
                 "Audit hash-chain verification failed.", "critical", False, 3600),
    ),
))
