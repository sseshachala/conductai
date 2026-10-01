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

## Inspect registered tool results

For an enrolled server, set **JSON response inspection** in Integrations and save.
The CLI uses the same setting:

```sh
conduct guard mcp-review response_policy --server SERVER_UUID --revision CURRENT_REVISION --mode block
```

- `off`: existing behavior, the default.
- `audit`: record detected secret types and response-rule decisions; return the result unchanged.
- `block`: withhold detected secrets and results denied by response rules.
- `redact`: replace detected secrets; response-rule blocks still withhold the result.

This applies to registered workflow MCP calls and registered Slack MCP output.
It does not inspect an editor's direct MCP traffic. Response policy evaluation
uses provider `mcp`, the tool name as model, and the `response` gate. Detection
uses the existing secret patterns and configured response rules, not a general
malicious-content classifier.

Enabled inspection buffers a single JSON HTTP response before releasing it.
The response is limited to 1 MiB, 10,000 inspected nodes and 32 nesting levels.
Text and structured JSON are supported; SSE, binary/resource content, compressed
responses and redirects are rejected. Calls are not retried or redirected to
another transport. The existing catalog review still runs before invocation.

Audit storage must be available before dispatch and before release. A changed
registration, revoked approval, unavailable policy engine or failed inspection
withholds the result, including in audit mode. This cannot undo upstream tool
side effects. Audit entries contain decisions and finding types, not result text.

Private-key fixture coverage is pending in [#2317](https://github.com/sseshachala/conductai/issues/2317)
because ConductGuard blocks that synthetic fixture. No rule exception or bypass
is included here.

## Link device inventory to registrations

Open **Settings > Tool Setup > MCP inventory**. Administrators can select a
workspace registration and link it to a discovered MCP reference. Members can
view the links. Use **Review registered servers** to inspect, approve, quarantine,
or revoke a registration.

The CLI supports the same workflow on the selected deployment:

```sh
conduct guard discover
conduct guard mcp-links list
conduct guard mcp-links link --installation AGENT_UUID --reference REFERENCE_ID --server SERVER_UUID --revision 0
conduct guard mcp-links unlink --installation AGENT_UUID --reference REFERENCE_ID --revision 1
```

Use `agent_id`, `reference_id`, and the installation's `revision` from `list`.
Pass `--offset NEXT_OFFSET` for another page. A stale scan must be refreshed
before creating a link. Removed references and deleted registrations remain
visible until an administrator unlinks them. Unlinking does not delete or
change the registered server.

Links are administrator associations, not automatic endpoint matches. They
identify a configuration reference on one installation, not its current URL,
process, or credentials. Discovery does not upload these values or contact
the server. Changing a reference's target requires reviewing its association.
Identical names on different devices are never automatically linked.

Discovery, registration review, and device traffic are separate columns.
An approved registered catalog does not prove that an editor uses Conduct's
execution path. Device traffic stays **Not observed** and endpoint identity
stays **Unverified** until correlated evidence is implemented. Links never
grant access, approve a catalog, or change enforcement.

Scans cannot overwrite links. Link changes require workspace administrator
permission, a current revision, and an audit entry. Registration details are
looked up in the same workspace; URLs and saved credentials are not returned
by this inventory endpoint.

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

Apply migrations through `0160` before starting the updated API. `0159` adds
nullable review state to `mcp_servers`; `0160` adds administrator associations
to `discovered_agents`. Existing records retain their behavior. Rollback
refuses to discard review state or inventory associations. Use the matching
CLI build for `mcp-review`, `mcp-links`, and usage metadata; this change does
not publish a CLI release.
