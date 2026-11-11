# Stream the Guard audit log to a SIEM

`conduct audit feed` writes every Guard audit event (allow, warn, block, approval, gateway
attempt) as one NDJSON line. Any log collector that tails a file can ship it to your SIEM:
Splunk Universal Forwarder, Azure Monitor Agent (Microsoft Sentinel), Falcon LogScale
Collector (CrowdStrike Next-Gen SIEM), Fluent Bit, or Vector.

The feed is served by the `get_audit_feed` MCP tool. The CLI calls it with your agent token,
so no extra API access is needed.

## Requirements

- `conduct-cli` 0.15.0 or later, logged in with `conduct login`.
- The logged-in user needs the `platform.audit_log.view` permission (Security role or above).

## Run the feed

```bash
# Catch up from the last 24 hours, then keep polling every 60 seconds
conduct audit feed --follow --output /var/log/conduct/audit.ndjson
```

| Option | Default | Meaning |
|---|---|---|
| `--since` | last 24 hours | ISO-8601 start for a new feed. Ignored once a cursor is saved. |
| `--follow` | off | Keep polling. Without it the command exits when caught up. |
| `--interval` | 60 | Seconds between polls with `--follow`. |
| `--limit` | 500 | Events per request (1–1000). |
| `--state` | `~/.conduct/audit-feed.cursor` | Cursor checkpoint. Delete it to start over. |
| `--output` | stdout | Append to this file instead of stdout. |
| `--sink` | none | Push to `splunk-hec` or `sentinel` instead of writing a file. See Push delivery. |

Run it under your usual process supervisor (for example a service manager or a container
restart policy) so it restarts after a reboot or crash. Rotate the output file with
`copytruncate`, since the feed keeps the file open.

**Delivery.** The cursor is saved after each page is written, so restarting the command resumes
where it stopped. If it stops between writing a page and saving the cursor, that page is written
again: deduplicate on the event `id`. Events younger than 60 seconds are held back until
in-flight writes settle, so no event is skipped.

**Integrity.** Each event carries `previous_hash` and `entry_hash`. Verify a contiguous file
offline with `conduct audit verify <file>`.

Starting a feed (a call without a cursor) is itself recorded in the audit log as
`audit.feed_start`.

## Check the feed is flowing

The **Audit** page in the app shows a **SIEM feed** card. It lists each collector, when it last pulled, and how far behind it is. A collector is marked **Stale** after 15 minutes with no pull. In Lens or any MCP client, `get_audit_feed_status` returns the same data. Both need `platform.audit_log.view`.

## Push delivery (optional)

Instead of writing a file for a collector, the CLI can push events straight to a SIEM. Use
`--sink` instead of `--output`; the two are mutually exclusive.

**Delivery guarantee.** Events are sent in batches (up to 500 events or about 900 KB). The
cursor is saved only after the destination acknowledges every batch of a page. A failed request
is retried with exponential backoff and jitter (1s, 2s, 4s, up to 60s) for HTTP 408, 429, 5xx and
network errors, honouring `Retry-After`; other 4xx responses are not retried. If retries run out
(8 attempts by default) the command exits non-zero and the cursor stays where it was, so a
restart resumes from the last acknowledged page. A crash mid-page can send that page again:
deduplicate on the event `id`.

**Secrets.** Tokens and client secrets are read from a file or an environment variable, never
from the command line, and are not written to logs or error messages. Keep the files readable
only by the collector user.

Push sinks send the native JSON event (the `--format` option applies to file output only).

### Splunk HTTP Event Collector

```bash
conduct audit feed --follow --sink splunk-hec \
  --hec-url https://splunk.example.com:8088 \
  --hec-token-file /etc/conduct/hec-token \
  --hec-index conduct
```

Sends to `<hec-url>/services/collector/event` with `sourcetype=conduct:guard:audit`, so the
`props.conf` stanza above applies. The token can also come from `CONDUCT_HEC_TOKEN`. Create the
HEC token for the `conduct` index, with indexer acknowledgement off (the HTTP 200 response is the
acknowledgement used here).

### Microsoft Sentinel (Logs Ingestion API)

```bash
conduct audit feed --follow --sink sentinel \
  --dce-url https://my-dce.eastus-1.ingest.monitor.azure.com \
  --dcr-id dcr-0123456789abcdef \
  --stream Custom-ConductAudit_CL \
  --tenant-id <tenant> --client-id <app-id> \
  --client-secret-file /etc/conduct/entra-secret
```

Setup:

1. Register an Entra app and create a client secret.
2. Create a data collection endpoint and a data collection rule with a custom stream
   `Custom-ConductAudit_CL` whose input columns match the feed fields (a `TimeGenerated` column is
   added to every record from `ts`), and a destination custom table `ConductAudit_CL`.
3. Grant the app the **Monitoring Metrics Publisher** role on the data collection rule.

`--tenant-id` and `--client-id` can come from `AZURE_TENANT_ID` and `AZURE_CLIENT_ID`; the
secret from `CONDUCT_SENTINEL_CLIENT_SECRET`. Access tokens are cached and refreshed
automatically.

## Collector examples

### Splunk Universal Forwarder

```ini
# inputs.conf
[monitor:///var/log/conduct/audit.ndjson]
sourcetype = _json
index = conduct
```

### Microsoft Sentinel (Azure Monitor Agent)

Create a data collection rule with a **Custom Text Logs** data source that points at
`/var/log/conduct/audit.ndjson`, sends to a custom table such as `ConductAudit_CL`, and parses
each line with `parse_json(RawData)` in the transformation.

### CrowdStrike Falcon LogScale / Next-Gen SIEM (Falcon LogScale Collector)

```yaml
sources:
  conduct_audit:
    type: file
    include: /var/log/conduct/audit.ndjson
    sink: logscale
sinks:
  logscale:
    type: humio
    token: <ingest token>
    url: <your LogScale URL>
```

Assign the JSON parser to the ingest token's repository.

### Fluent Bit

```ini
[INPUT]
    Name   tail
    Path   /var/log/conduct/audit.ndjson
    Parser json
    Tag    conduct.audit
```
