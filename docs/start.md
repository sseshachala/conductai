# Start

New to Conduct. Zero to a first working automation.

---

## Install

```bash
pip install conduct-cli
```

Requires Python 3.9+. Runs on Linux, macOS, and Windows.

Verify:

```bash
conduct --version
```

For local development against the Conduct codebase (docker-compose, migrations, seeded data), see [Developer setup](modules/conductguard/developer_setup.md) instead.

---

## Quickstart

Five commands from install to a first agent run against your own GitHub repo.

### 1. Log in

```bash
conduct login
```

Opens a browser, authenticates against `api.conductai.ai` (or your self-hosted server), and stores the token at `~/.conduct/config.json`. Token starts with `cond_agt_`.

Prefer manual? Issue a token from **Settings → Agents → Issue token** in the dashboard, then:

```bash
conduct login --server https://api.conductai.ai --token cond_agt_xxx --workspace <workspace-id>
```

### 2. Browse playbooks

```bash
conduct playbooks
```

Lists the 30+ pre-built playbooks (PR review, incident response, security scanning, dependency updates, etc.). See the full catalog in [Examples](examples.md).

### 3. Install all playbooks into a project

```bash
conduct install-all --project DevOps --repo owner/repo
```

Creates the project if it doesn't exist. Instantiates every playbook, pointed at your GitHub repo. Use `--input key=value` to override any playbook input.

### 4. List installed agents

```bash
conduct agents
```

### 5. Fire a test run

```bash
conduct test "PR Reviewer"
```

Streams the agent's execution live. Use `conduct test --all` to fire every agent in sequence.

That's it. Your repo now has 30+ AI agents watching for PRs, incidents, dependency updates, and security issues — governed by Guard and logged to a hash-chained audit trail.

---

## Your first `playbook.yaml`

A playbook is a YAML file describing an agent's inputs, trigger, and block sequence. Minimum viable:

```yaml
name: My First Agent
version: 1
description: >
  Says hello in Slack when triggered.

inputs:
  slack_channel:
    label: Slack channel
    default: "#general"

trigger:
  type: webhook

blocks:
  - id: greet
    type: slack_post
    channel: {{ inputs.slack_channel }}
    text: "hello from conduct"
```

Save as `hello.yaml`, drop into `apps/api/playbooks/` (self-hosted) or upload via the dashboard (hosted). Trigger by POSTing to `https://<your-api>/webhooks/inbound/<workflow-id>`.

Next: read [Playbooks](mental-models/08-playbooks.md) for the full block reference, or browse [Examples](examples.md) for 37 working playbooks to copy from.

---

## Next steps

- **Understand what just happened** → [Concepts](README.md#concepts) (start with [Execution engine](mental-models/01-execution-engine.md))
- **Add governance** → [ConductGuard Quickstart](modules/conductguard/QUICKSTART.md)
- **Wire into CI, MCP, or your own tools** → [Automate](automate.md)
- **Run Conduct on your own infrastructure** → [Developer setup](modules/conductguard/developer_setup.md)
