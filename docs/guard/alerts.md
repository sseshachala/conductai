# Alerts and notifications

All alert routing lives on one page: **Guard > Connections > Notifications**
(`/theguard/connections/notifications`). It lists each alertable source, its
events, and the channels (Slack, email, PagerDuty, webhook) that receive them.

Gateway profile pages only carry an **Alerts** link, which opens this page
filtered to that profile (`?source=gateway:<profile_id>`).

## Sources and events

| Source | Events |
| --- | --- |
| Guard rules | block, warn, audit, approval, fail-open, drift (unchanged) |
| Gateway profile | admission refused (429), spend cap refused (503), upstream 5xx, upstream timeout, rate limit exceeded |
| Audit feed | collector stale (alerts when a SIEM collector stops pulling for 15 minutes, and once more when it recovers) |
| Audit chain | verification failed (registered; not raised yet, see #2524) |

Adding a channel to a gateway event without a profile filter covers every
profile; with the filter it covers that profile only.

## Storm control

- Alerts are grouped per (profile, event) over a 60 second window, so a burst of
  refusals sends one message, not one per request.
- Each channel has a dedupe window (default 5 minutes): at most one delivery per
  window for the same profile and event.
- Each channel can set a threshold in events per minute; the channel only fires
  at or above it.
- Audit feed alerts fire once on the stale transition and once on recovery.

## Notes

- Gateway alerts are derived by the worker from recent gateway audit rows. They
  add nothing to request handling. Delivery can lag by up to about a minute.
- Admission refusals (429 at the gateway door) are not yet raised: they are
  refused before a profile is resolved and before an audit row is written.
- Webhook URLs must be public https and are re-validated on every send.

## API

`GET /guard/alerts/registry`, `GET|POST /guard/alerts`,
`PATCH|DELETE /guard/alerts/{id}`. Writes need `guard.settings.edit`.
Guard-rule channels continue to use `/guard/notifications`.

## Adding a source

Register it in `apps/api/app/modules/guard/notification_registry.py` with
`register_source(SourceDef(...))` and raise events with
`dispatch_alert(...)` from `app/modules/guard/alert_dispatch.py`. The page
renders from the registry, so no UI change is needed.
