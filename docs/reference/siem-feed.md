# Stream the Guard audit log to a SIEM

`conduct audit feed` writes every Guard audit event (allow, warn, block, approval, gateway
attempt) as one NDJSON line. Any log collector that tails a file can ship it to your SIEM:
Splunk Universal Forwarder, Azure Monitor Agent (Microsoft Sentinel), Falcon LogScale
Collector (CrowdStrike Next-Gen SIEM), Fluent Bit, or Vector.

The feed is served by the `get_audit_feed` MCP tool. For a long-running collector, use a
dedicated feed token (below) so the feed does not depend on one person's login.

## Requirements

- `conduct-cli` 0.15.0 or later.
- Either a feed token (recommended for collectors), or `conduct login` as a user with the
  `platform.audit_log.view` permission (Security role or above).

## Feed token (recommended)

A feed token is owned by the workspace, not a person. It keeps working when the person who
created it leaves, and it can read the audit feed only: every other API and MCP tool refuses it.

1. In the app, open **Audit**, then the **SIEM feed** card, then **Feed tokens**. Enter a name
   and choose **Create token**. This needs the workspace admin role (`platform.workspace.edit`).
2. Copy the token (`cond_feed_...`). It is shown once and only its hash is stored.
3. Put it in a file readable only by the collector user, then point the CLI at it:

```bash
install -m 600 /dev/null /etc/conduct/feed-token   # then paste the token into it
conduct audit feed --follow --token-file /etc/conduct/feed-token \
  --output /var/log/conduct/audit.ndjson
```

You can also set `CONDUCT_FEED_TOKEN` in the collector's environment. The token is never
accepted as a command-line argument, so it does not appear in process listings. Revoke a token
from the same card; the collector stops authenticating immediately. The SIEM feed card labels
collectors that use a token as **service token**.

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
| `--token-file` | none | File holding a feed token. `CONDUCT_FEED_TOKEN` is the env alternative. Without either, the logged-in user's token is used. |
| `--output` | stdout | Append to this file instead of stdout. |

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
