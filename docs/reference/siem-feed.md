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
| `--format` | `json` | `json`, `ocsf`, `ecs` or `cef`. See Output formats. |
| `--output` | stdout | Append to this file instead of stdout. |
| `--sink` | none | Push to `splunk-hec` or `sentinel` instead of writing a file. See Push delivery. |

Run it under your usual process supervisor (for example a service manager or a container
restart policy) so it restarts after a reboot or crash. Rotate the output file with
`copytruncate`, since the feed keeps the file open.

### Run as a service

The CLI does not install a service for you. Use one of these templates. Each runs the feed
with a feed token, restarts it on failure, and keeps its cursor in a fixed place so a restart
resumes where it stopped. Replace `/usr/local/bin/conduct` with the output of `which conduct`.

**Linux (systemd).** Create a `conduct` system user that owns `/etc/conduct/feed-token`
(mode 600), `/var/lib/conduct` and `/var/log/conduct`. Save this as
`/etc/systemd/system/conduct-audit-feed.service`:

```ini
[Unit]
Description=Conduct Guard audit feed
After=network-online.target
Wants=network-online.target

[Service]
User=conduct
ExecStart=/usr/local/bin/conduct audit feed --follow \
  --token-file /etc/conduct/feed-token \
  --state /var/lib/conduct/audit-feed.cursor \
  --output /var/log/conduct/audit.ndjson
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Then, as root, run `systemctl daemon-reload && systemctl enable --now conduct-audit-feed`.
Check it with `systemctl status conduct-audit-feed` and `journalctl -u conduct-audit-feed`.

**macOS (launchd).** Save this as `/Library/LaunchDaemons/ai.conductai.audit-feed.plist`
(owned by root, mode 644), then, as root, run
`launchctl bootstrap system /Library/LaunchDaemons/ai.conductai.audit-feed.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>ai.conductai.audit-feed</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/conduct</string>
    <string>audit</string><string>feed</string><string>--follow</string>
    <string>--token-file</string><string>/etc/conduct/feed-token</string>
    <string>--state</string><string>/var/lib/conduct/audit-feed.cursor</string>
    <string>--output</string><string>/var/log/conduct/audit.ndjson</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardErrorPath</key><string>/var/log/conduct/audit-feed.err</string>
</dict>
</plist>
```

**Container.** Run the same command with a restart policy, for example
`docker run -d --restart unless-stopped` with the token file and a state volume mounted, and
pass the same `--token-file`, `--state` and `--output` paths.

To send events straight to Splunk HEC or Sentinel instead of a file, replace `--output ...` with
`--sink` (see [Push delivery](#push-delivery-optional)). If a collector stops, the **SIEM feed** card marks it **Stale**
after 15 minutes, and the `collector_stale` alert can notify a Slack or webhook channel.

**Delivery.** The cursor is saved after each page is written, so restarting the command resumes
where it stopped. If it stops between writing a page and saving the cursor, that page is written
again: deduplicate on the event `id`. Events younger than 60 seconds are held back until
in-flight writes settle, so no event is skipped.

**Integrity.** Each event carries `previous_hash` and `entry_hash`. Verify a contiguous file
offline with `conduct audit verify <file>`.

Starting a feed (a call without a cursor) is itself recorded in the audit log as
`audit.feed_start`.

## Truncation checkpoints on each page

Every page returned by `get_audit_feed` also carries `checkpoint` (the latest signed
chain-head checkpoint for the workspace, or `null` until the first one is taken) and
`audit_keys` (the public keys needed to verify it, `key_id` to `{alg, public_key, created_at}`).
`conduct audit feed` writes events only; to check a checkpoint save a page and run
`conduct audit verify export.ndjson --checkpoint page.json --keys https://<api-host>/.well-known/conduct-audit-keys`.
A SIEM that stores the latest checkpoint can later prove the chain tail was not cut back past it.
See [Audit log verification](../audit-log-verification.md#signed-chain-head-checkpoints-tail-truncation).

## Check the feed is flowing

The **Audit** page in the app shows a **SIEM feed** card. It lists each collector, when it last pulled, and how far behind it is. A collector is marked **Stale** after 15 minutes with no pull. In Lens or any MCP client, `get_audit_feed_status` returns the same data. Both need `platform.audit_log.view`.

## Output formats

`--format` chooses the line format. The default, `json`, is the native schema and is what
`conduct audit verify` reads. The other formats are for collectors and SIEMs that expect a
standard schema. Every format keeps the hash-chain fields (`previous_hash`, `entry_hash`,
`chain_position`), and any field the mapping does not know is carried through, so a newer
server never loses data in an older CLI.

| Format | Value | One line is | Chain fields live in |
|---|---|---|---|
| Native | `json` (default) | JSON object | top-level fields |
| OCSF 1.3 | `ocsf` | JSON object | `unmapped` |
| Elastic ECS 8.x | `ecs` | JSON object | `conduct.chain`, and `event.hash` |
| ArcSight CEF | `cef` | one CEF line | `cs4` (entry hash), `cs5` (previous hash), `cn1` (position) |

```bash
conduct audit feed --follow --format ocsf --output /var/log/conduct/audit.ocsf.ndjson
```

A file written with `--format ocsf|ecs|cef` is not verifiable with `conduct audit verify`.
Keep a `json` copy, or verify from the `previous_hash` / `entry_hash` values in the converted
lines.

### OCSF: why API Activity

Events map to OCSF class **API Activity (6003)**, category Application Activity. Every event is an
agent tool call plus Guard's decision on it, and most are allowed calls, so an activity class
fits. A Detection Finding class would turn every allow into a finding. Decisions are expressed
with `action_id` / `disposition_id` and `severity_id`, so detections can still key on them.

| Native | OCSF |
|---|---|
| `ts` | `time` (epoch ms) |
| `id` | `metadata.uid` |
| `chain_position` | `metadata.sequence` |
| `workspace_id` | `metadata.tenant_uid` |
| `tool_call` | `api.operation` |
| `ai_tool` | `api.service.name`, `actor.app_name`, `src_endpoint.name` |
| `clerk_user_id`, `user_email` | `actor.user.uid`, `actor.user.email_addr` |
| `session_id` | `actor.session.uid` |
| `rule_message` or `input_summary` | `message` |
| `allowed` | `action_id` 1, `disposition_id` 1, `severity_id` 1 |
| `warned` | `action_id` 1, `disposition_id` 19 (Alert), `severity_id` 3 |
| `blocked` | `action_id` 2, `disposition_id` 2, `severity_id` 4, `status_id` 2 |
| approval required | `action_id` 99, `severity_id` 3 |
| `decision`, `rule_id`, hash fields, everything else | `unmapped` |

### ECS

`@timestamp`, `event.{id,action,outcome,category,type,hash,sequence,dataset}`, `user.{id,email}`,
`rule.{id,description}`, `organization.id` (the workspace), `service.name` (the AI tool),
`log.level`. Blocks and warnings use `event.category: intrusion_detection`. Product-specific
fields are under `conduct.*`: `conduct.decision`, `conduct.tool_call`,
`conduct.chain.{previous_hash,entry_hash,position}`.

### CEF

```
CEF:0|Conduct|Guard|1|guard.blocked|Bash blocked|8|rt=1788264060000 externalId=... act=blocked outcome=failure app=claude_code suser=... cs1Label=ruleId cs1=... cs2Label=toolCall cs2=Bash cs3Label=workspaceId cs3=... cs4Label=entryHash cs4=... cs5Label=previousHash cs5=... cn1Label=chainPosition cn1=42
```

Severity is 1 (allowed), 5 (warned), 6 (approval required), 8 (blocked). Fields without a CEF
slot are added as `conduct<FieldName>` keys, for example `conductHashVersion`.

## Parser configuration

### Splunk

Native JSON, written to a file the Universal Forwarder monitors. `inputs.conf` on the
forwarder:

```ini
[monitor:///var/log/conduct/audit.ndjson]
sourcetype = conduct:guard:audit
index = conduct
```

`props.conf` on the indexer or heavy forwarder (and the search head, for search-time fields):

```ini
[conduct:guard:audit]
INDEXED_EXTRACTIONS = json
KV_MODE = none
SHOULD_LINEMERGE = false
LINE_BREAKER = ([\r\n]+)
TIME_PREFIX = "ts":"
# ISO-8601 with or without fractional seconds: let Splunk detect the format
MAX_TIMESTAMP_LOOKAHEAD = 40
TRUNCATE = 100000
FIELDALIAS-conduct_user = user_email AS user
EVAL-action = case(decision=="blocked","blocked", decision=="allowed","allowed", true(), "unknown")
```

A restart can write one page twice, so deduplicate with `| dedup id` in searches. For `--format cef`, use `sourcetype = cef` with the CEF Splunk add-on.
For `--format ocsf`, use the Splunk OCSF add-on or keep `INDEXED_EXTRACTIONS = json` with
`TIME_PREFIX = "time":` and `TIME_FORMAT = %s%3N`.

### Microsoft Sentinel

Collect the file with the Azure Monitor Agent. Create a **Custom Text Logs** data collection rule (DCR):
file pattern `/var/log/conduct/audit.ndjson`, record delimiter end-of-line, destination a
custom table `ConductAudit_CL`. The text-log stream has one `RawData` column, so parse it in the
DCR `transformKql`:

```kusto
source
| extend d = parse_json(RawData)
| project TimeGenerated = todatetime(d.ts),
          EventId = tostring(d.id),
          ChainPosition = tolong(d.chain_position),
          WorkspaceId = tostring(d.workspace_id),
          AiTool = tostring(d.ai_tool),
          ToolCall = tostring(d.tool_call),
          Decision = tostring(d.decision),
          RuleId = tostring(d.rule_id),
          RuleMessage = tostring(d.rule_message),
          UserEmail = tostring(d.user_email),
          UserId = tostring(d.clerk_user_id),
          AgentIdentityId = tostring(d.agent_identity_id),
          SessionId = tostring(d.session_id),
          PreviousHash = tostring(d.previous_hash),
          EntryHash = tostring(d.entry_hash),
          Raw = d
```

Give the custom table the matching columns (`TimeGenerated` datetime, the rest string except
`ChainPosition` long and `Raw` dynamic). If you prefer to keep `RawData` and parse at query time,
save this as a workspace function named `ConductAudit`:

```kusto
ConductAudit_CL
| extend d = parse_json(RawData)
| project TimeGenerated = todatetime(d.ts), EventId = tostring(d.id), Decision = tostring(d.decision),
          ToolCall = tostring(d.tool_call), AiTool = tostring(d.ai_tool), RuleId = tostring(d.rule_id),
          UserEmail = tostring(d.user_email), EntryHash = tostring(d.entry_hash), d
```

### CrowdStrike Falcon LogScale / Next-Gen SIEM

Create a parser for the repository (**Parsers > New parser**) and assign it to the ingest token:

```
parseJson(field=@rawstring)
| parseTimestamp(field=ts, format="yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX", timezone="UTC")
| @timestamp := ts
| @id := id
| event.dataset := "conduct.guard.audit"
| event.outcome := if(decision=="blocked", then="failure", else="success")
| user.email := user_email
| drop([ts])
```

If you ship `--format ecs`, the parser is `parseJson(field=@rawstring) | parseTimestamp(field="@timestamp", format="yyyy-MM-dd'T'HH:mm:ss[.SSSSSS]XXX", timezone="UTC")`.

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
