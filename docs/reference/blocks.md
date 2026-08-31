# Playbook block reference

Every block type a playbook can use. Source of truth: [`apps/api/app/dsl/schema.py`](../../apps/api/app/dsl/schema.py).

A playbook YAML has three top-level sections that hold blocks:

- **`on:`** — trigger definitions (event → entry block)
- **`blocks:`** — the main graph, keyed by block id
- **`cleanup:`** — blocks that always run at the end (success OR failure)

Every block under `blocks:` sets a `type:` from the enum below. Every block can optionally set `label`, `description`, `next` (routing), `retry`, `fallback_block`, and `for_each` (iteration).

---

## Quick index

| Type | Purpose |
|---|---|
| [`tool`](#tool) | Call an integration action (GitHub, Slack, HTTP, shell, ...) |
| [`brain`](#brain) | LLM step — single-turn or agentic multi-turn |
| [`logic`](#logic) | Branching — `pass` / `fail` on a `condition` |
| [`approval`](#approval) | Human-in-the-loop gate via Slack, email, or both |
| [`memory`](#memory) | Read or write persisted state (repo or workspace scope) |
| [`output`](#output) | Deliver the final result (Slack, email, both) |
| [`guard`](#guard) | Explicit Guard policy check inside the graph |
| [`mcp`](#mcp) | Invoke an MCP server tool |
| [`trigger`](#trigger) (top-level `on:`) | Event → entry block |
| [`cleanup`](#cleanup) (top-level `cleanup:`) | Always-runs teardown |

---

## Every block shares

```yaml
my-block-id:
  type: tool               # required — one of the enum above
  label: "Human name"      # optional — shown on canvas
  description: >           # optional — free text (brain blocks also treat this as prompt input)
    What this block does.
  next: another-block-id   # routing — string for linear, dict for logic branches
  retry:                   # optional retry policy
    max_attempts: 3
    backoff: exponential
  fallback_block: on-fail  # optional — where to route when retries exhausted
  for_each: "{{ items.output }}"   # optional — iterate; item bound to `item` (or item_var)
  item_var: pr             # optional — rename the loop variable
```

---

## <a id="tool"></a>`tool`

Call an integration action. The most common block type.

**Required:** `integration`, `action` (or use slash-form `action: github/create_issue`).
**Params live under:** `params:` (or `input:` — alias).

```yaml
open-issue:
  type: tool
  integration: github
  action: create_issue
  params:
    repo: "{{ inputs.repo }}"
    title: "Autopilot: {{ inputs.title }}"
    body: "{{ compose.output }}"
  next: notify-slack
```

Shorthand:

```yaml
open-issue:
  type: tool
  action: github/create_issue   # integration derived from prefix
  params: { ... }
```

**Integrations available:** GitHub, Slack, HTTP, run_shell, PagerDuty, Sentry, DataDog, and more — see `apps/api/app/runtime/integrations/`.

---

## <a id="brain"></a>`brain`

Runs an LLM step. Two modes:

- **`mode: single`** — one turn, JSON out. Use for classification, extraction, decisions.
- **`mode: agentic`** — multi-turn with tools. Use for planning + execution.

**Required:** one of `description`, `system`, `prompt`, or `prompt_file` (relative path to `prompts/*.txt` next to the playbook).

```yaml
triage:
  type: brain
  mode: single
  model: claude-haiku-4-5-20251001
  description: >
    Classify this issue as bug / feature / question. Return
    {"kind": "bug|feature|question", "priority": "p0|p1|p2|p3"}.
  next: route
```

Agentic example with tool scope + turn budget:

```yaml
implement-fix:
  type: brain
  mode: agentic
  model: claude-sonnet-4-6
  complexity: medium         # small | medium | large — resolves to max_turns
  max_turns: 40              # override (optional)
  allowed_tools: [Read, Edit, Bash, Grep]
  system: "You implement targeted fixes to close a GitHub issue."
  prompt: "Issue: {{ issue.body }}"
  execution_policy:
    disallow_paths: ["node_modules", "vendor"]
    require_tests: true
  sandbox: auto              # auto | e2b | modal | proxy
  next: open-pr
```

Remote host execution (optional):

```yaml
runs_on:
  ip: "{{ target.ip }}"
  credentials_from: digitalocean   # integration handle providing SSH auth
  username: root
```

---

## <a id="logic"></a>`logic`

Branch on a Jinja condition.

**Required:** `condition` and `next: { pass: <id>, fail: <id> }`.

```yaml
gate:
  type: logic
  condition: "{{ triage.priority in ['p0', 'p1'] }}"
  next:
    pass: page-oncall
    fail: file-ticket
```

---

## <a id="approval"></a>`approval`

Human-in-the-loop gate. Blocks the run until a human approves or rejects.

**Required:** `via` (`slack` | `email` | `both`, defaults to `slack` when a channel is set) plus at least one destination.

```yaml
prod-push-gate:
  type: approval
  via: slack
  channel: "#deploys"
  message: "Approve prod push? Plan: {{ plan.output }}"
  next: apply-config
```

Email gate:

```yaml
compliance-review:
  type: approval
  via: email
  approval_email: security@acme.com
  message: "Please review: {{ finding.description }}"
```

Approval decisions land at `POST /webhooks/approval/<run-id>/<decision>`. See [`apps/api/playbooks/self-driving-network-approval-demo.yaml`](../../apps/api/playbooks/self-driving-network-approval-demo.yaml) for a full HITL example.

---

## <a id="memory"></a>`memory`

Read or write persisted key/value state.

**Required:** `action: read` or `action: write`. Write requires `summary:`.

```yaml
recall:
  type: memory
  action: read
  scope: repo
  key: "last-triage-{{ inputs.repo }}"
  limit: 5
  next: brain-step

record:
  type: memory
  action: write
  scope: workspace
  key: "postmortem-{{ incident.id }}"
  summary: "{{ triage.output }}"
```

**Scopes:** `repo` (per-repo namespace) or `workspace` (org-wide).

---

## <a id="output"></a>`output`

Deliver the final result of the run.

**Required:** either an `output:` section, or `channels:` + `template:` shorthand.

```yaml
notify:
  type: output
  channels: [slack]
  template: |
    :robot_face: Autopilot finished
    PR: {{ open-pr.url }}
```

Long form:

```yaml
notify:
  type: output
  output:
    channels: [slack, email]
    slack:
      channel: "#eng"
    email:
      to: team@acme.com
    template: "{{ summary.output }}"
```

---

## <a id="guard"></a>`guard`

Explicit Guard policy check. Fires a `guard_check` mid-graph — useful when a following block would otherwise bypass the proxy (e.g. an inline shell call that doesn't hit an LLM).

```yaml
pre-write-check:
  type: guard
  params:
    intent: file_write
    path: "{{ target.path }}"
  next: apply-patch   # blocked → run halts with decision reason
```

Guard events written by this block land in the same hash-chained audit trail as proxy + hook + MCP events. See [`docs/mental-models/03-guard-proxy.md`](../mental-models/03-guard-proxy.md).

---

## <a id="mcp"></a>`mcp`

Invoke a tool on any MCP server the workspace has installed.

**Required:** `tool_name` plus one of `config.server_name`, `config.provider`, or `credential_key`.

```yaml
peekaboo-shot:
  type: mcp
  config:
    server_name: peekaboo         # workspace-installed MCP server
    tool_name: screenshot
    inputs:
      window_title: "Chrome"
  next: analyse
```

Or by provider handle:

```yaml
list-linear-issues:
  type: mcp
  config:
    provider: linear              # marketplace-registered provider
    tool_name: list_issues
  credential_key: linear_token
```

MCP invocations flow through Guard's [MCP router](../modules/conductguard/conductguard_mcp.md); the workspace `credential_key` is redacted from logs.

---

## <a id="trigger"></a>`trigger` (top-level `on:`)

Triggers live under the top-level `on:` key, not inside `blocks:`. The key is the event name; the value's `next:` names the entry block.

```yaml
on:
  github.pull_request.opened:
    integration: github
    next: triage           # entry block; default = first key under blocks:
    branches: [main]       # event-specific filters allowed (extra fields OK)

  webhook:
    next: handle
```

Common trigger types: `github.*`, `slack.*`, `webhook`, `schedule`, `pagerduty.*`, `manual`. See `apps/api/app/runtime/triggers/` for the full list.

---

## <a id="cleanup"></a>`cleanup` (top-level `cleanup:`)

Cleanup blocks always run at the end — success or failure. Same shape as any block, except **no `next:`** (they're unreachable from the main graph).

```yaml
cleanup:
  release-lock:
    type: tool
    action: redis/del
    params:
      key: "lock-{{ inputs.repo }}"
```

Use for: releasing locks, cleaning temporary branches, closing sessions, posting a run summary.

---

## Iteration (`for_each`)

Any block can be run once per item in a list.

```yaml
review-each:
  type: brain
  mode: single
  description: "Review PR {{ pr.number }}"
  for_each: "{{ list-prs.output }}"
  item_var: pr           # default: `item`
```

The block executes serially per item. Outputs are collected as `<block-id>.output = [<per-item>, ...]`. Full pattern in [`bulk-pr-reviewer.yaml`](../../apps/api/playbooks/bulk-pr-reviewer.yaml).

---

## See also

- [Concepts → Playbooks](../mental-models/08-playbooks.md) — mental model
- [Concepts → Brain block](../mental-models/02-brain-block.md) — how brain blocks compile
- [Concepts → DSL compiler](../mental-models/06-dsl-compiler.md) — YAML → DAG
- [ADR-0004 — Playbook DSL vs external orchestration frameworks](../adr/ADR-0004-playbook-dsl-versus-external-orchestration-frameworks.md) — design rationale
- [Examples](../examples.md) — 37 working playbooks
