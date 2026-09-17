# MCP / Flight Recorder canary

This is a **decision-recording load canary**, not yet an upstream MCP execution
benchmark. It drives real MCP requests through `/guard/mcp` or `/mcp`. It never
POSTs synthetic events to Flight Recorder and never runs the checked commands.

## Contract

Each Locust user has a distinct agent identity token. It initializes a session,
acknowledges initialization, discovers tools, and verifies its workspace via
`guard_status`. Then it repeatedly calls `guard_check` with a unique `canary_call`
marker as the first input field. Session churn repeats the handshake. Both
`Mcp-Session-Id` and Conduct's `X-Session-Id` are sent, because the legacy endpoint
uses the latter for audit correlation.

Every attempted check is committed to a local SQLite ledger **before sending**.
No automatic HTTP retries: a timeout has an uncertain server outcome, not an
assumed failure to execute. The run fails on transport/protocol failures even if
their records later appear. Pending ledger rows survive an interrupted process.

After load stops, an observer reads `/guard/events`. It checks exactly one record
per call, with the expected workspace, authenticated agent identity, session,
tool, decision, and source. The correlation marker is in supported `tool_input`,
not an invented request-header contract. Overlapping pages are deduplicated by
event ID; different event IDs for the same call are flagged as duplicates.

Current API pagination uses offsets. Two identical settled scans are required;
scan limits or observer failures cannot produce a pass. This is an operational
check, not a proof against records arriving after the drain window. The observer
measures REST visibility, **not** dashboard rendering or SSE delivery latency.

## Setup

### Two-agent local Docker smoke

With the existing `conduct-e2e-api`, `pgvector/pgvector:pg16`, and
`redis:7-alpine` images available, and the Python dependencies below installed:

```sh
rtk proxy scripts/mcp-canary/.venv/bin/python scripts/mcp-canary/local_smoke.py \
  --agents 2 --output scripts/mcp-canary/results/local-001
```

This starts a separate `conduct-mcp-canary` Compose project, migrates its own
PostgreSQL database to the checked-out code, and serves the real API on
`127.0.0.1:3120`. Existing Docker workspaces/databases are untouched. It seeds
synthetic local users, memberships, and expiring encrypted agent credentials;
this is not a Clerk signup test. HTTP authentication is not mocked. No Clerk
or provider keys are supplied. The fixture uses the database owner, so this
does not prove RLS isolation. It uses the existing API image dependencies with
the checked-out application source mounted read-only.

The default endpoint is `/mcp`; add `--endpoint /guard/mcp` to check the legacy
endpoint. Add `--unconfigured` to deliberately omit Guard installation and
assert every check is blocked and recorded with the authenticated identity.
Load is capped at two requests/sec for 15 seconds, with at most 40
requests. Credentials remain in memory/private subprocess pipes, are revoked
after the run, and are never written to reports. The API stops afterward;
the database retains synthetic accounts and audit evidence. Re-running creates
a fresh workspace. A new ephemeral encryption key is used each run, so this
stack must never contain non-canary credentials. PostgreSQL/Redis remain
available for inspection. Do not run local smoke instances concurrently.

### Configurable runner

Python 3.11+:

```sh
rtk proxy python3 -m venv scripts/mcp-canary/.venv
rtk proxy scripts/mcp-canary/.venv/bin/pip install -r scripts/mcp-canary/requirements.txt
```

Create a dedicated workspace using the existing admin flow. Mint distinct scoped
agent credentials and an observer credential authorized to read its events.
Supply secrets through your secret manager/environment, **never JSON, arguments,
committed files, or report artifacts**. `example.json` contains only environment
variable names and placeholder identity/workspace UUIDs. Use a local ignored
configuration such as `local.json` with real IDs, never real tokens.

An agent count of 100 means 100 entries and distinct credentials, not one token
with 100 spoofed identity headers. All agents must exercise every scenario or
the report fails coverage. Increase duration/request budget to accommodate the
handshake, ramp, and reconnects. Tokens are only held in process memory.

```sh
rtk proxy scripts/mcp-canary/.venv/bin/python scripts/mcp-canary/run.py \
  --config scripts/mcp-canary/local.json \
  --output scripts/mcp-canary/results/baseline-001
```

Remote targets additionally require an explicit origin + workspace approval:

```sh
rtk proxy scripts/mcp-canary/.venv/bin/python scripts/mcp-canary/run.py \
  --config scripts/mcp-canary/local-staging.json \
  --output scripts/mcp-canary/results/staging-001 \
  --approve-target 'https://YOUR-STAGING-API|YOUR-CANARY-WORKSPACE-UUID'
```

Every output directory must be new. Exit 0 means all checks passed; exit 1 means
failed. Configuration errors exit nonzero before load. Inspect `report.html`,
`report.json`, and `ledger.sqlite`; artifacts omit response bodies, input payloads,
emails, and credentials. Reports include per-agent latency and error counts and
per-call reconciliation failure IDs. They are local artifacts, not a public page.

## Controls and scenarios

- `rps`: global **all MCP requests** cap, including initialization/discovery.
- `concurrency`: maximum simultaneous HTTP requests; independent of agent count.
- `spawn_rate`: identities started per second; `duration_seconds` includes ramp.
- `max_requests`: hard all-request budget. No unbounded soak default.
- `reconnect_every`: checks per session before reinitialization; 0 disables churn.
- `timeout_seconds`: HTTP timeout; requests have no automatic retries.
- `abort_error_rate`, `abort_p95_ms`: stop admission after the first 20 completed
  requests when thresholds are exceeded. In-flight work drains with a bound.
- `min_achieved_rps_ratio`: insufficient throughput fails instead of claiming
  capacity. This is a capped closed-loop workload, not an open-loop arrival test.
- Generator event-loop lag p99 >=250ms fails; latency excludes generator queue
  wait, while achieved throughput includes the ramp and graceful shutdown.
- Observer traffic is separate, at most ten pages/sec after load, with a bounded
  drain and page count. Do not run concurrent canaries in the same workspace.

Start with the allowed scenario. For blocking, install a dedicated rule matching
`mcp_canary_block`, then add:

```json
{"name":"block","tool_name":"mcp_canary_block","tool_input":{},"decision":"blocked"}
```

For an allow response recorded by an audit-only policy, set
`"decision": "allowed", "audit_decision": "audited"`. The local smoke does this
for `mcp-audit-all-tool-calls`. Both verdicts are checked exactly; the runner
does not silently accept alternate audit decisions.

Use only synthetic, non-sensitive inputs. Disable external notification fan-out
for canary policy rules; block load must not flood Slack, email, or PagerDuty.
Disable behavioral anomaly rules in the dedicated baseline workspace, or test
them separately: they may legitimately produce additional records. Warning and
approval scenarios need different expected cardinality and are not supported
by this initial one-record contract.

## Regression gates

The initial local run found that MCP `_record_event` omitted `agent_identity_id`.
The accompanying fix resolves the authenticated identity on both transports and
passes it into the shared writer. Missing attribution remains a hard failure.
Both endpoints now block `guard_check` / `guard_check_prompt` when GuardConfig
is absent, instead of treating missing setup as an empty permissive ruleset.
Onboarding remains responsible for provisioning Guard. A configured workspace
with an intentionally empty ruleset is not equivalent to missing setup.
`guard_check` records decisions, not tool completion; no durable inference
lifecycle is assumed for these rows.

## Rollout and remaining work

1. Run harness unit/HTTP fixture tests. These prove the harness, not Conduct.
2. Run a small canary against a real local/staging Conduct deployment; fix any
   attribution, missing-record, duplicate, or session-correlation defects.
3. In staging, ramp 100 -> 500 -> 1,000 identities, raising RPS separately. Capture
   API CPU/memory, DB pool waits/locks, Redis health, and unrelated-tenant latency.
4. Approve a capped production baseline only after staging passes. A separate
   workspace is data isolation, not infrastructure isolation. Keep an operator
   and external service-health monitor present; this runner's breaker only sees
   its own traffic. No scheduled production load is installed by this change.

Before claiming full MCP gateway capacity, add separate work for:
- Controlled upstream MCP tools + execution receipts, failures, delays, and
  cancellation. Prove blocks never reach upstream and retries do not double-run.
- Real database/worker outage recovery and connection exhaustion in staging.
- Audit hash-chain integrity under concurrent writes; run the existing full-chain
  verifier separately in the dedicated workspace, not repeatedly during load.
- MCP SSE/streaming transport, server-initiated traffic, and UI/SSE visibility.
- Cross-workspace denial tests and policy/credential rotation during load.
- Provision/revoke automation (never export plaintext minted tokens), independent
  agent-count/arrival-rate sweeps, distributed generators, and CI manual dispatch.
- Shared-infrastructure kill switch and agreed capacity SLOs before production
  stress. Benchmark thresholds in the example are guardrails, not product SLOs.

## Harness tests

```sh
rtk proxy scripts/mcp-canary/.venv/bin/pip install pytest
rtk proxy scripts/mcp-canary/.venv/bin/python -m pytest -q scripts/mcp-canary/test_canary.py
```

Tests include actual local HTTP fixtures exercising initialization, discovery,
allowed/blocked decisions, reconnects, pagination, and report generation, including
a 100-agent run. Missing identity, missing records, and HTTP-200 JSON-RPC errors
must produce FAIL. No live workspace is created by these tests.

Load scheduling uses [Locust's library API](https://docs.locust.io/en/stable/use-as-lib.html).
