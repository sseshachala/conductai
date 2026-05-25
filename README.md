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

## 9 ready-made playbooks

Install any of these in one click, configure credentials, and run.

| Playbook | Trigger | What it does |
|----------|---------|-------------|
| **Autopilot Git → Slack** | GitHub issue label | Implements fix, opens PR, posts to Slack |
| **Dependency Updater** | Weekly cron | Bumps patch/minor deps, opens PR |
| **Incident Responder** | PagerDuty / OpsGenie webhook | Correlates commits, posts hypothesis to Slack |
| **Release Notes** | Git tag | Reads merged PRs, writes CHANGELOG, posts to #releases |
| **Issue Triage** | GitHub issue opened | Labels, prioritises, posts clarifying comment |
| **Deploy Monitor** | Vercel / Railway webhook | Monitors deployment, alerts on failure |
| **PR Review** | GitHub PR opened | Reviews diff, posts structured feedback |
| **Scheduled Report** | Daily cron | Aggregates Linear issues, emails summary |
| **Custom Agent** | Any trigger | Build from scratch on the canvas |

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
