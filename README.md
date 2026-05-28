# Conduct

**YAML playbooks that turn AI agents into reusable team automations.**

Label a GitHub issue `ai-ready` → an agent clones your repo, writes the fix, runs tests, and opens a draft PR. One-click Approve or Reject before anything merges.

[![MIT License](https://img.shields.io/badge/license-MIT-blue)](LICENSE)
[![Stars](https://img.shields.io/github/stars/sseshachala/conductai?style=social)](https://github.com/sseshachala/conductai/stargazers)
[![conductai.ai](https://img.shields.io/badge/hosted-conductai.ai-black)](https://conductai.ai)

> ⭐ If this saves you time, star it — it helps others find it.

---

<!-- Record a 30-second demo and drop it here:
![Conduct demo](docs/demo.gif)
-->

## What it does

Conduct runs AI agents on a drag-and-drop canvas (or in YAML). Agents have real tool access — they read code, call APIs, open PRs, post to Slack. You control what they can touch and approve before anything ships.

```
GitHub issue labeled "ai-ready"
  → Brain block (Claude) reads the issue, clones the repo, writes the fix
  → Tool block opens a draft PR
  → Approval block pauses — Slack DM: [Approve] [Reject]
  → Output block posts result to #eng channel
```

Every step is visible. Every run is logged. Nothing merges without a human in the loop.

---

## Why teams pick Conduct

| Problem | Conduct's answer |
|---------|-----------------|
| Autonomous agents (Devin, Cursor) are black boxes | Live trace, event log, and approval gates on every run |
| Zapier / n8n have no AI in the middle | Brain blocks are agentic — Claude reads your codebase, iterates, hands off |
| One shared credential set across all agents | Per-agent environments — each agent gets its own scoped credentials |
| Hard to move from demo to production | Human-in-the-loop by design — nothing merges without approval |
| Agent errors disappear into a void | Structured logs + Sentry integration — every failure is captured and triageable |

---

## 18 ready-made playbooks

Install any of these in one click, configure credentials, and run. Grouped by the 10 categories you'll see in the Marketplace.

### Issue → PR
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Autopilot Quick** | GitHub issue labeled | Implements fix, opens PR immediately (CI runs tests on the PR) |
| **Autopilot Full** | GitHub issue labeled | Implements fix, runs tests with retry, opens PR |
| **Autopilot + Approval** | GitHub issue labeled | Implements fix, runs tests, human approves in Slack, then opens PR |

### Code Review
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **PR Reviewer** | PR opened | Reviews the diff for bugs, security, and style; posts a review |
| **Copilot / AI PR Reviewer** | PR opened by Copilot/Cursor/Claude Code | Extra scrutiny for hallucinated APIs and missing tests; human approves before merge |
| **Security Scanner** | PR opened | Scans for OWASP Top 10, hardcoded secrets, auth bypasses; posts report, files fix issue for criticals |

### Issue Triage
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Issue Triage** | GitHub issue opened | Classifies type and priority, adds labels, posts a clarifying comment if vague |

### CI/CD
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **CI Failure Alert** | CI build fails | Diagnoses the failed step, posts root cause and suggested fix to Slack |
| **Flaky Test Detective** | Repeated CI failures | Identifies flaky tests, finds the offending commit, posts a fix recommendation |

### Release Management
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Release Readiness Reviewer** | Release branch cut | Checks open blockers, failed CI, pending reviews; posts a go/no-go summary |
| **Release Notes Drafter** | Git tag pushed | Reads merged PRs, groups by type, writes CHANGELOG, posts to Slack |

### Incidents & Ops
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Incident Responder** | PagerDuty / OpsGenie webhook | Correlates recent commits and deploys, posts root cause hypothesis to Slack |
| **Postmortem Drafter** | Incident resolved | Reads timeline, alerts, and commits; drafts a structured postmortem |

### Security
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Dependency Updater** | Weekly cron | Bumps patch/minor deps, opens a single clean PR |
| **Security Patch Updater** | Dependabot alert | Applies the security patch, runs tests, opens a PR with CVE reference |

### Docs
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Docs Drift Detector** | PR merged | Checks if related docs/README/runbooks went stale; opens a docs PR or files an issue |

### Platform & Infra
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Terraform Plan Reviewer** | Terraform plan PR opened | Reviews for security misconfigs, cost anomalies, and drift; posts findings |

### Testing
| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Smoke Test** | Manual / CI | Minimal 1-step pipeline ping for CI gating and worker health checks |

---

## Block types

| Block | What it does |
|-------|-------------|
| **Trigger** | Starts a run — webhook, cron, or manual |
| **Brain** | Agentic Claude step with tool access and bounded autonomy |
| **Tool** | Deterministic API call — GitHub, Slack, Linear, Vercel, Railway |
| **Logic** | Branch on pass / fail |
| **Approval** | Pauses the run, sends Slack DM with Approve / Reject |
| **Output** | Sends formatted summary via Slack or email |
| **Cleanup** | Always runs last — tear down resources, close loops |

---

## Integrations

| Integration | Actions |
|-------------|---------|
| **GitHub** | clone repo, push file, create branch, open PR, merge PR, add secret |
| **Slack** | post message, send DM, handle approval buttons |
| **Linear** | fetch / create / update issues, add comments |
| **Vercel** | list / get / wait for deployments |
| **Railway** | trigger / monitor deployments |
| **DigitalOcean** | create / destroy droplets |
| **Email** | send via Resend or SendGrid |

---

## Architecture

```
apps/
  web/          Next.js — canvas UI, run feed, settings
  api/          FastAPI + SQLAlchemy + Alembic
  api/worker.py Background run executor (Redis queue)
packages/
  conduct-cli/  Python CLI — trigger agents from terminal or CI
```

---

## Quick start (self-hosted)

### Prerequisites

- Docker + Docker Compose
- Anthropic API key

### 1. Clone and configure

```bash
git clone https://github.com/sseshachala/conductai.git
cd conductai
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
ENCRYPTION_KEY=<32-char random string>
```

### 2. Start

```bash
docker compose up -d
docker compose exec api alembic upgrade head
```

### 3. Open

- **UI**: http://localhost:3000
- **API docs**: http://localhost:8000/docs

### 4. Create your first agent

1. **Projects** → New project
2. **Agents** → New agent (or pick a template)
3. **Settings → Environments** → add GitHub + Slack credentials
4. Assign the environment to your agent on the canvas
5. Hit **Run**

---

## Quick start (CLI)

```bash
pip install conduct-cli

conduct --server https://api.conductai.ai \
        --api-key YOUR_CLI_API_KEY \
        run autopilot.yaml
```

```yaml
# autopilot.yaml
name: Fix GitHub Issue
workflow_id: <your-workflow-id>
workspace_id: <your-workspace-id>

trigger:
  event_type: github_issue_labeled
  label: ai-ready
  repo:
    full_name: your-org/your-repo

issue:
  number: 42
  title: "Button not responding on mobile"
  body: "Tap on submit — nothing happens on iOS Safari."
```

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ENCRYPTION_KEY` | Yes | 32-byte key for credential encryption |
| `DATABASE_URL` | Yes | Postgres connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `API_BASE_URL` | Yes | Public API URL (for webhook callbacks) |
| `CLI_API_KEY` | Optional | Shared secret for CLI / CI access |
| `SLACK_SIGNING_SECRET` | Optional | Verifies Slack interactive payloads |
| `RESEND_API_KEY` | Optional | Email output via Resend |
| `SENTRY_DSN` | Optional | Error capture — unhandled exceptions + block failures |
| `CLERK_SECRET_KEY` | Optional | Enables Clerk authentication |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Optional | Clerk frontend key |

---

## Deployment

### API + worker (Render)

1. New Web Service → connect GitHub → root directory: `apps/api`
2. Add a **PostgreSQL** database and a **Redis** instance
3. Add a second service (same repo, root `apps/api`, start command: `python -m app.worker`)
4. Set environment variables above
5. After first deploy: run `alembic upgrade head` via Render shell

### Frontend (Vercel)

1. Connect GitHub repo → root directory: `apps/web`
2. Set `NEXT_PUBLIC_API_URL=https://api.conductai.ai`
3. Preview deployments created automatically for every PR

---

## Webhooks

| Endpoint | Service | Events |
|----------|---------|--------|
| `POST /webhooks/vercel` | Vercel | deployment.succeeded / failed |
| `POST /webhooks/railway` | Railway | DEPLOY_SUCCESS / FAILED / CRASHED |
| `POST /webhooks/slack/interactions` | Slack | Approval button clicks |
| `POST /webhooks/inbound/{workflow_id}` | Any | Generic JSON trigger |

---

## Security

- All credentials encrypted at rest (AES-256-GCM) — decrypted only at point of use
- Per-workspace environments — agents only access credentials you assign
- Audit log — every credential change, workflow create/delete, and run trigger recorded (admin-only)
- Approval gates — human confirmation before any action ships to production
- Sentry integration — block failures captured with `run_id`, `block_id`, `workspace_id` tags

---

## Contributing

PRs welcome. Open an issue first for anything beyond a small fix.

```bash
git clone https://github.com/sseshachala/conductai.git
cd conductai
docker compose up -d
docker compose exec api alembic upgrade head
```

---

## License

MIT — use it, fork it, build on it.
