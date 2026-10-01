# MCP review and session usage

## Review a registered MCP server

In **Integrations**, select **Require review**, then **Inspect tools**.
Review the names, descriptions, and schemas before selecting **Approve inspected tools**.
Enabling review stops registered-server execution until approval.
Existing registrations are unchanged until review is enabled or they are quarantined.

The CLI uses the selected deployment and workspace:

```sh
conduct guard mcp-review list
conduct guard mcp-review require_review --server SERVER_UUID --revision 0
conduct guard mcp-review inspect --server SERVER_UUID
conduct guard mcp-review approve --server SERVER_UUID --revision 1 --digest INSPECTED_DIGEST
conduct guard mcp-review quarantine --server SERVER_UUID --revision 2
conduct guard mcp-review restore --server SERVER_UUID --revision 3
```

Use the current revision from `list`. Restore requires a fresh inspection and approval.
`revoke --yes` deletes the credential saved on this registration and denies its
Conduct calls. It does not revoke an upstream provider token, an Integration
vault credential, or a federation grant.

Review changes require `platform.workspace.edit`; inspection requires
`platform.credentials.manage`. Mutations are workspace-scoped and audited.
Concurrent or stale changes are rejected.

Before resolving an enrolled registration for execution, Conduct fetches its
tool catalog and checks the approved digest. Changed descriptions, schemas,
annotations, added tools, or removed tools block execution. A failed catalog
check also blocks. Updating the registration invalidates its approval.

This applies to Conduct's registered-server resolver, including MCP workflow
blocks and registered Slack MCP output. It does not wrap an editor's direct
MCP connection or the separate legacy credential-key execution path. Passive
device discovery does not contact servers, enroll findings, or establish trust.
Quarantine affects subsequent resolutions; an already-authorized in-flight call
is not cancelled. Catalog hashes detect changes, not whether a tool is malicious.
Tool-result inspection and redaction are not part of this change.

## Session usage

Updated CLI collectors preserve ordinary input, cache reads, cache writes and
output for Claude Code, Codex CLI/Desktop and Copilot CLI. Reasoning, when
available, remains a subset of output and is not counted twice. Codex model
changes and Claude message model labels are retained when present. Missing
model/provider information stays unknown; the tool name is not a provider.

Activity details show reported categories, observation time, pricing version,
and an estimate when the API has an exact applicable rate. Unknown models,
missing provider information, missing cache rates, unspecified cache-write
durations, and missing request counts remain unpriced. These are token-rate
estimates, not subscription invoices.

Client reports are marked **unreconciled with Gateway** and **excluded from
budgets**. Estimates are stored as evidence, not added to Gateway charges,
session billed cost, or enforceable budget totals. Request-level matching and
combined spend rollups remain separate work.

Collectors keep their existing workspace/deployment checks, offline journal,
snapshot deduplication and counter-reset handling. The new transcript cursor
format starts with a baseline on upgrade; it does not import old history.
No prompts, tool arguments, or transcript text are included in usage reports.
Cursor/Windsurf session counters remain unavailable; live editor acceptance is
still pending.

## Deployment

Apply migration `0159` before starting the updated API. It adds nullable review
state to `mcp_servers`. Existing records retain their behavior. Schema rollback
refuses to discard enrolled review state. Use the matching CLI build for the
new `mcp-review` command and usage metadata; this PR does not publish a release.
