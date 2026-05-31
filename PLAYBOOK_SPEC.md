# Conduct Playbook Specification

A **playbook** is a YAML file that defines an AI agent workflow — what triggers it, what steps it runs, and how those steps connect. This document is the canonical reference for authoring Conduct playbooks.

---

## Table of Contents

- [Top-Level Structure](#top-level-structure)
- [Params](#params)
- [Triggers (`on`)](#triggers-on)
- [Blocks](#blocks)
  - [brain](#brain--ai-inference)
  - [tool](#tool--integration-action)
  - [logic](#logic--conditional-branch)
  - [approval](#approval--human-gate)
  - [memory](#memory--read--write-context)
  - [output](#output--send-results)
- [Cleanup Blocks](#cleanup-blocks)
- [Template Variables](#template-variables)
- [Routing](#routing)
- [Validation Rules](#validation-rules)
- [Full Example](#full-example)

---

## Top-Level Structure

```yaml
name: <string>           # Required. Unique identifier (used as slug).
version: 1               # Optional. Schema version (default: 1).
description: <string>    # Optional. Human-readable summary.

params:                  # Optional. Install-time parameters.
  <param_name>:
    type: string | number | boolean
    required: false
    default: <value>
    description: <string>

inputs:                  # Optional. Canvas UI configuration (dropdowns, text fields).
  <input_name>:
    label: <string>
    type: select | text | number
    default: <value>
    options: [...]       # For type: select

on:                      # Optional. Trigger definitions.
  <event_type>:
    integration: <string>
    next: <block_id>
    # event-specific filter fields

blocks:                  # Required. The workflow DAG.
  <block_id>:
    type: brain | tool | logic | approval | memory | output
    # block-specific fields
    next: <block_id> | { pass: <id>, fail: <id> }

cleanup:                 # Optional. Always-run teardown blocks.
  <block_id>:
    type: tool | brain
    # same fields as blocks, no `next`
```

---

## Params

Declared at the top level under `params:`. Referenced anywhere in the YAML as `{{params.<name>}}`. Users set these at install time or run time.

```yaml
params:
  environment:
    type: string
    required: true
    description: "Target environment (staging or production)"
  notify_slack:
    type: boolean
    default: true
```

---

## Triggers (`on`)

Declared under `on:`. The key is the event type. Multiple triggers can be listed.

```yaml
on:
  github.issue_labeled:
    integration: github
    labels: ["autopilot ready"]
    label_mode: one_of    # fire if any listed label matches
    next: fetch_issue

  webhook:
    next: process_payload

  manual:
    next: start_block
```

### Supported Trigger Types

| Event | Integration | Filters |
|---|---|---|
| `github.issue_labeled` | `github` | `labels` (array), `label_mode` |
| `github.push` | `github` | `branches` (array), `ref` |
| `webhook` | — | none (full payload in `{{_trigger}}`) |
| `manual` | — | none |

All triggers support:
- `integration` — credential handle to use
- `next` — first block to run (defaults to first block if omitted)

---

## Blocks

All blocks share these optional fields:

```yaml
label: <string>          # Display name in the canvas UI
description: <string>    # Human note (not sent to the model)
next: <routing>          # See Routing section
```

---

### `brain` — AI Inference

Runs a Claude model. The `description` is the full prompt.

```yaml
blocks:
  analyze:
    type: brain
    model: claude-haiku-4-5-20251001   # Optional. Defaults to workspace model.
    mode: single                        # single (default) | agentic
    description: |
      Analyze the pull request diff below and identify any security issues.

      PR diff: {{fetch_pr.diff}}

      Output ONLY valid JSON on the last line:
        {"issues": [...], "severity": "low|medium|high"}
    next: check_severity
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `description` | Yes | The full prompt. Supports template variables. |
| `model` | No | Claude model ID. Default: `claude-haiku-4-5-20251001` |
| `mode` | No | `single` = one-shot response. `agentic` = multi-turn with tool use. |
| `custom_instructions` | No | Appended to description at runtime. |
| `runs_on` | No | SSH into a remote host before running (see below). |
| `guard` | No | ConductGuard policy config for this block (see below). |

**Remote execution (`runs_on`):**

```yaml
runs_on:
  ip: "{{provision_server.ip}}"
  credentials_from: digitalocean   # Integration handle for SSH key
  username: root
  port: 22
```

**Guard config (`guard`):**

Link specific ConductGuard policies to a brain block. Policies are defined in your team's ConductGuard library and referenced by rule ID. Requires ConductGuard to be installed on the workspace — ignored gracefully if not.

```yaml
guard:
  policies:
    - no-rm-rf                # block recursive deletes
    - no-hardcoded-secrets    # warn on secrets in file edits
    - approve-prod-deploy     # require Slack approval before production deploys
    - audit-migrations        # silently log all migration file changes
  on_violation: halt          # halt | warn | continue
```

| Field | Required | Description |
|---|---|---|
| `policies` | Yes | List of rule IDs from the team's ConductGuard policy library |
| `on_violation` | No | `halt` = stop the run (default). `warn` = log and continue. `continue` = audit only. |

Different blocks in the same playbook can have different guard configs:

```yaml
blocks:
  analyze_code:
    type: brain
    mode: agentic
    guard:
      policies: [no-hardcoded-secrets]
      on_violation: warn          # non-critical — warn and continue

  deploy_to_production:
    type: brain
    mode: agentic
    guard:
      policies: [approve-prod-deploy, audit-migrations]
      on_violation: halt          # critical — stop and require approval
```

When a guard policy fires:
- `halt` — run stops, violation logged in ConductGuard dashboard, Slack notified if configured
- `warn` — run continues, violation flagged in dashboard
- `continue` — audit record written silently, no interruption

**Brain block output:** The entire text response is available as `{{block_id.output}}`. If the response ends with a JSON object, its keys are also available directly: `{{block_id.issues}}`, `{{block_id.severity}}`, etc.

---

### `tool` — Integration Action

Calls a specific action on a connected integration (GitHub, Slack, etc.).

```yaml
blocks:
  fetch_issue:
    type: tool
    integration: github
    action: fetch_issue
    params:
      owner: "{{_trigger.repo_owner}}"
      repo: "{{_trigger.repo_name}}"
      issue_number: "{{_trigger.issue_number}}"
    next: analyze
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `integration` | Yes | Integration handle (e.g. `github`, `slack`, `linear`) |
| `action` | Yes | Action to call on that integration |
| `params` | No | Key-value arguments for the action (open dict) |

**Tool block output:** Each action returns a dict. Fields are available as `{{block_id.<field>}}`.

---

### `logic` — Conditional Branch

Routes the workflow based on a condition.

```yaml
blocks:
  tests_pass:
    type: logic
    condition: "{{run_tests.passed}} == true"
    next:
      pass: open_pr
      fail: notify_failure
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `condition` | Yes | Expression that evaluates to truthy/falsy |
| `next.pass` | Yes | Block to run if condition is true |
| `next.fail` | Yes | Block to run if condition is false |

---

### `approval` — Human Gate

Pauses execution and waits for a human to approve or reject.

```yaml
blocks:
  approve_deploy:
    type: approval
    message: "Deploy {{params.version}} to production?"
    via: slack
    channel: "#engineering"
    next:
      pass: deploy
      fail: abort
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `message` | No | Message shown to approver |
| `via` | No | `slack` (default if channel set) \| `email` \| `both` |
| `channel` | No | Slack channel (e.g. `#engineering`) |
| `slack_user` | No | Slack user ID to DM |
| `approval_email` | No | Email address to send approval link to |

At least one of `channel`, `slack_user`, or `approval_email` must be set.

---

### `memory` — Read / Write Context

Persists and recalls context across workflow runs.

```yaml
blocks:
  recall_context:
    type: memory
    action: read
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    limit: 5
    next: analyze

  record_outcome:
    type: memory
    action: write
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    summary: |
      Issue #{{_trigger.issue_number}} — {{analyze.type}} / {{analyze.priority}}
    next: notify
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `action` | Yes | `read` or `write` |
| `scope` | Yes | `repo` (scoped to a repo) \| `workspace` (shared across all runs) |
| `key` | Yes | Lookup key (usually a repo name or workflow ID) |
| `limit` | No | `read` only — max number of entries to return (default: 10) |
| `summary` | No* | `write` only — template string to store. *Required for write. |

**Read output:** `{{block_id.entries}}` — array of prior summaries. Use in brain descriptions:

```yaml
description: |
  {% if recall_context.entries %}
  Prior context:
  {% for entry in recall_context.entries %}
  - {{entry.summary}}
  {% endfor %}
  {% endif %}
```

---

### `output` — Send Results

Sends a message to Slack or email. Optionally includes Approve/Reject buttons.

```yaml
blocks:
  notify_success:
    type: output
    label: Notify PR ready
    output:
      via: slack
      slack:
        channel: "#engineering"
        approval: true   # Adds Approve / Reject buttons

  notify_email:
    type: output
    output:
      via: email
      email:
        to: "{{params.notify_email}}"
```

**Fields:**

| Field | Required | Description |
|---|---|---|
| `output.via` | Yes | `slack` \| `email` \| `both` |
| `output.slack.channel` | If via=slack | Target channel |
| `output.slack.approval` | No | `true` adds interactive Approve/Reject buttons |
| `output.email.to` | If via=email | Recipient address |
| `output.email.from_address` | No | Override sender address |

---

## Cleanup Blocks

Declared under the top-level `cleanup:` key (not `blocks:`). These always run when the workflow ends — whether it succeeded, failed, or was cancelled. Use for teardown (e.g. destroying a provisioned server).

```yaml
cleanup:
  teardown_server:
    type: tool
    integration: digitalocean
    action: destroy_droplet
    params:
      droplet_id: "{{provision_server.droplet_id}}"
```

Cleanup blocks do not support `next` routing — they all run in parallel at workflow end.

---

## Template Variables

All string fields support [Jinja2](https://jinja.palletsprojects.com/) templating.

| Variable | Description |
|---|---|
| `{{_trigger}}` | Full trigger payload (webhook body or GitHub event) |
| `{{_trigger.repo_owner}}` | GitHub repo owner (for GitHub triggers) |
| `{{_trigger.repo_name}}` | GitHub repo name |
| `{{_trigger.repo_full_name}}` | `owner/repo` format |
| `{{_trigger.issue_number}}` | GitHub issue number |
| `{{_trigger.clone_url}}` | Repo clone URL |
| `{{params.<name>}}` | Install-time parameter value |
| `{{inputs.<name>}}` | Canvas input value |
| `{{<block_id>.<field>}}` | Output field from a previous block |
| `{{<block_id>.output}}` | Full text output from a brain block |

**Conditionals and loops:**

```yaml
{% if some_block.entries %}
  {% for entry in some_block.entries %}
  - {{entry.summary}}
  {% endfor %}
{% endif %}
```

---

## Routing

The `next` field controls flow after a block completes.

```yaml
# Unconditional — always go to this block
next: block_id

# Conditional — used by logic and approval blocks
next:
  pass: block_id_on_success
  fail: block_id_on_failure
```

All `next` targets must reference a valid block ID in the same playbook.

---

## Validation Rules

These are enforced at load time — invalid playbooks are rejected before running:

- `name` must be a non-empty string
- All `next` targets must exist as block IDs in `blocks:`
- `tool` blocks require both `integration` and `action`
- `brain` blocks require `description`; `mode` must be `single` or `agentic`
- `logic` blocks require `condition` and `next: {pass, fail}`
- `approval` blocks require at least one of: `channel`, `slack_user`, `approval_email`
- `memory` blocks require `action` (`read` or `write`), `scope`, and `key`; `write` requires `summary`
- `output` blocks require an `output` section with a valid `via` and matching channel config

---

## Full Example

A complete playbook that watches for issues labeled "autopilot ready", implements the fix, runs tests, and opens a PR:

```yaml
name: autopilot-github-issues
version: 1
description: >
  Watch for GitHub issues labeled 'autopilot ready'. Clone the repo, implement the fix,
  run tests, and open a pull request. Notifies #engineering on success or failure.

inputs:
  trigger_label:
    label: Trigger label
    type: select
    default: "autopilot ready"
    options:
      - "autopilot ready"
      - "ai-fix"
  model:
    label: AI model
    type: select
    default: claude-sonnet-4-6
    options:
      - claude-haiku-4-5-20251001
      - claude-sonnet-4-6

on:
  github.issue_labeled:
    integration: github
    labels: ["{{inputs.trigger_label}}"]
    label_mode: one_of
    next: recall_context

blocks:
  recall_context:
    type: memory
    label: Recall prior context
    action: read
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    limit: 5
    next: fetch_issue

  fetch_issue:
    type: tool
    label: Fetch issue
    integration: github
    action: fetch_issue
    params:
      owner: "{{_trigger.repo_owner}}"
      repo: "{{_trigger.repo_name}}"
      issue_number: "{{_trigger.issue_number}}"
    next: implement_fix

  implement_fix:
    type: brain
    label: Implement fix
    mode: agentic
    model: "{{inputs.model}}"
    description: |
      You are an expert software engineer. An issue has been labeled for autonomous fixing.

      Issue: #{{fetch_issue.issue_number}} — {{fetch_issue.title}}
      Body: {{fetch_issue.body}}
      Repo: {{_trigger.repo_full_name}}
      Clone URL: {{_trigger.clone_url}}

      {% if recall_context.entries %}
      Prior context for this repo:
      {% for entry in recall_context.entries %}
      - {{entry.summary}}
      {% endfor %}
      {% endif %}

      Steps:
      1. Clone the repo and create a branch: fix/issue-{{fetch_issue.issue_number}}
      2. Read the relevant files and implement the fix
      3. Commit with message: "fix: <description> (closes #{{fetch_issue.issue_number}})"
      4. Push the branch

      Output ONLY valid JSON on the last line:
        {"branch_name": "fix/issue-...", "summary": "one line description of the fix"}
    next: run_tests

  run_tests:
    type: brain
    label: Run tests
    mode: agentic
    model: "{{inputs.model}}"
    description: |
      The branch {{implement_fix.branch_name}} has been pushed to {{_trigger.repo_full_name}}.

      1. Clone the branch
      2. Run the test suite (detect: pytest, npm test, go test, etc.)
      3. If tests fail, fix the failures and push again (max 3 attempts)

      Output ONLY valid JSON on the last line:
        {"passed": true, "attempts": 1, "output": "brief summary"}
    next: check_tests

  check_tests:
    type: logic
    label: Tests passed?
    condition: "{{run_tests.passed}} == true"
    next:
      pass: open_pr
      fail: notify_failure

  open_pr:
    type: brain
    label: Open PR
    mode: agentic
    model: "{{inputs.model}}"
    description: |
      Open a pull request for branch {{implement_fix.branch_name}} on {{_trigger.repo_full_name}}.

      PR title: "fix: {{implement_fix.summary}} (closes #{{fetch_issue.issue_number}})"
      Base branch: main

      Use the GitHub API to create the PR.

      Output ONLY valid JSON on the last line:
        {"pr_url": "https://github.com/..."}
    next: record_outcome

  record_outcome:
    type: memory
    label: Record outcome
    action: write
    scope: repo
    key: "{{_trigger.repo_full_name}}"
    summary: |
      Issue #{{fetch_issue.issue_number}}: {{fetch_issue.title}}
      Fix: {{implement_fix.summary}}
      PR: {{open_pr.pr_url}}
    next: notify_success

  notify_success:
    type: output
    label: Notify success
    output:
      via: slack
      slack:
        channel: "#engineering"

  notify_failure:
    type: output
    label: Notify failure
    output:
      via: slack
      slack:
        channel: "#engineering"
```

---

## Supported Claude Models

| Model ID | Speed | Best For |
|---|---|---|
| `claude-haiku-4-5-20251001` | Fastest / cheapest | Triage, labeling, simple classification |
| `claude-sonnet-4-6` | Balanced | Most autopilot tasks, code review |
| `claude-opus-4-7` | Most capable | Complex multi-file refactors |

---

*Questions or issues with the spec? Open an issue at [github.com/sseshachala/conductai](https://github.com/sseshachala/conductai/issues).*
