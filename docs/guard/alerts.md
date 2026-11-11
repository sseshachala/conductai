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

## Vault-backed channels

PagerDuty, webhook and email channels reference a Vault entry instead of
holding a secret. Add the entry in Settings -> Vault, then pick it when adding
the channel (the page-level Vault selector decides which environment's entries
are offered).

| Channel | Vault service | Fields | `channel_ref` |
|---|---|---|---|
| PagerDuty | `pagerduty` | `routing_key` | non-secret label (`vault:<handle>`) |
| Webhook | `webhook` | `url`, optional `signing_secret` | non-secret label |
| Email | `email` (Resend/SendGrid) | existing email fields | recipient address |

- The channel stores `integration_id` (the Vault entry) and the credential is
  decrypted at send time, so rotating it in the Vault updates every channel
  that uses it. If the entry is deleted the channel is skipped and a warning
  is logged.
- Email: a channel with an email `integration_id` sends with that entry's
  credential. Without one it falls back to the workspace email credential, then
  the platform one.
- Webhook URLs saved to the Vault must pass the egress check (public https);
  every send re-validates and never follows redirects. The Vault "test" for
  `webhook` only runs that check and sends nothing; for `pagerduty` it only
  checks the key shape (32 letters/digits) and pages nobody.
- Rows that still carry a raw key/URL in `channel_ref` with no `integration_id`
  keep delivering unchanged. API responses mask those values and set
  `legacy_ref: true`; the UI shows "Typed key - move to Vault". There is no
  automatic migration of secrets.
- API responses include `vault_handle`, `environment_id` and `environment_name`
  for Vault-backed rows and never include credential values.
  `GET /credentials/integrations/vault?service=pagerduty|webhook|email|slack`
  lists entries (id, handle, environment) for the pickers.

### Webhook signature

When the Vault entry has a `signing_secret`, each request carries

```
X-Conduct-Signature: t=<unix seconds>,v1=<hex>
```

where `v1 = HMAC-SHA256(signing_secret, "<t>." + <raw request body>)`. Verify by
recomputing over the exact bytes received and rejecting stale `t` values.
Without a signing secret no header is sent.

## API

`GET /guard/alerts/registry`, `GET|POST /guard/alerts`,
`PATCH|DELETE /guard/alerts/{id}`. Writes need `guard.settings.edit`.
Guard-rule channels continue to use `/guard/notifications`.

## Adding a source

Register it in `apps/api/app/modules/guard/notification_registry.py` with
`register_source(SourceDef(...))` and raise events with
`dispatch_alert(...)` from `app/modules/guard/alert_dispatch.py`. The page
renders from the registry, so no UI change is needed.
