# SIEM detection content

Ready-made detections for the Guard audit feed (`conduct audit feed`, see
[docs/reference/siem-feed.md](../reference/siem-feed.md)): Splunk saved searches and Microsoft
Sentinel analytics rules.

| Detection | Signal | Severity |
|---|---|---|
| Repeated blocks | 5 or more `blocked` decisions from one agent identity or user in 10 minutes | Medium |
| Approval bypass attempt | An approval request was rejected, then the same user ran the same tool and it was allowed within 15 minutes, with no approval between | High |
| New MCP server first seen | `tool_call` of the form `mcp__<server>__<tool>` for a server with no call in the previous 14 days | Low |
| Kill-switch activation | `tool_call` ends with `deactivate_agent_identity` | High |
| Chain verification failure | An event's `previous_hash` is not the preceding event's `entry_hash` | High |

## Files

- `splunk/savedsearches.conf`: five scheduled searches. Assumes sourcetype `conduct:guard:audit`
  in index `conduct` (the `props.conf` in the feed docs).
- `sentinel/analytics-rules/*.yaml`: one scheduled analytics rule each, in the Sentinel
  content format. Import with the Sentinel repositories feature or paste the query.
- `sentinel/arm-template.json`: all five rules as one ARM deployment. Parameter `workspace` is
  the Log Analytics workspace name.

```bash
az deployment group create -g <resource-group> --template-file docs/siem/sentinel/arm-template.json \
  --parameters workspace=<workspace-name>
```

## Field names

The searches use the native feed schema (one JSON object per event). The fields used:

| Feed field | Splunk | Sentinel column (`ConductAudit_CL`) |
|---|---|---|
| `id` | `id` | `EventId` |
| `ts` | `_time` | `TimeGenerated` |
| `workspace_id` | `workspace_id` | `WorkspaceId` |
| `ai_tool` | `ai_tool` | `AiTool` |
| `tool_call` | `tool_call` | `ToolCall` |
| `decision` | `decision` | `Decision` |
| `rule_id`, `rule_message` | `rule_id`, `rule_message` | `RuleId`, `RuleMessage` |
| `user_email`, `clerk_user_id` | `user_email`, `clerk_user_id` | `UserEmail`, `UserId` |
| `agent_identity_id` | `agent_identity_id` | `AgentIdentityId` |
| `session_id` | `session_id` | `SessionId` |
| `previous_hash`, `entry_hash` | `previous_hash`, `entry_hash` | `PreviousHash`, `EntryHash` |

The Sentinel columns are the ones produced by the data collection rule transform in the feed
docs. If you ingest `--format ocsf` or `--format ecs`, map the same meanings: for example OCSF
`api.operation` is `tool_call` and ECS `event.action` is `tool_call`.

`decision` values: `allowed`, `warned`, `blocked`, `approval_pending`, `approved`, `rejected`.

## How each detection works, and its limits

- **Repeated blocks.** Groups by `agent_identity_id`, falling back to `clerk_user_id` then
  `user_email`, in fixed 10-minute buckets. Tune the threshold (`5`) and window to your traffic.
  Fixed buckets can split a burst across two windows; lower the threshold if that matters.
- **Approval bypass attempt.** A heuristic. Approval requests carry the requester's email while
  the approval decision carries the approver's, so the rule matches the rejection to the request
  on `tool_call` + `rule_id`, then looks for the requester running that `tool_call` again as
  `allowed`. A generic tool name (for example `Bash`) can match a legitimate later use; review
  before acting.
- **New MCP server.** Needs at least the lookback window of history in the SIEM (14 days; the
  Sentinel maximum for scheduled rules). With less history, every server looks new.
- **Kill switch.** Matches the call to the `deactivate_agent_identity` action in the feed. It
  fires when the client that made the call reported it to Guard (the agent hook or the MCP
  path); the server does not currently write a dedicated audit row for the deactivation, so a
  deactivation made some other way will not appear. Check the **Agent identity** page as the
  source of truth.
- **Chain verification failure.** Re-checks linkage in the SIEM: events ordered by time then
  `id` per workspace, each `previous_hash` must equal the previous `entry_hash`. It ignores the
  newest 20 minutes so late-arriving events are not mistaken for gaps, and it needs duplicates
  removed first (the feed is at-least-once, so the rules deduplicate on `id`). It detects a
  deleted, reordered or altered row; it does not recompute hashes, so it is not a replacement
  for `conduct audit verify <export.ndjson>`. Events without an `entry_hash` (older rows) are
  skipped. If the feed adds fields such as a hash version or signed checkpoints, the linkage
  check still applies.

## Tuning and alert volume

Scheduled rules re-evaluate overlapping windows. Sentinel rules alert on new matches only where
the query restricts to the newest rows (the approval rule does); for the others, turn on alert
grouping or suppression. In Splunk, throttle the alert (`alert.suppress = 1`,
`alert.suppress.period = 1h`, `alert.suppress.fields = workspace_id,actor`) if a burst is noisy.

## Validation

`apps/api/tests/test_siem_content.py` checks that the Sentinel YAML and ARM files parse and agree
with each other, and that every feed field the searches use exists in the audit export schema.
