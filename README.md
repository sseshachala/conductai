# Conduct

> **AI agents that act inside your stack — GitHub, Slack, Linear, and beyond.**

Conduct lets engineering teams build, run, and govern AI agents on a drag-and-drop canvas (or in YAML). Label a GitHub issue `ai-ready` → an agent clones your repo, writes the fix, runs tests, and opens a draft PR. One-click Approve or Reject in Slack before anything merges.

MIT licensed · Built for teams of 10–80 engineers · Every action is event-sourced and audit-logged.

---

## Why Conduct

| Problem | Conduct's answer |
|---------|-----------------|
| Autonomous agents (Devin, Cursor) are black boxes | Every step is visible — live trace, event log, approval gates |
| Zapier/n8n have no AI in the middle | Brain blocks are agentic — Claude reads your codebase, iterates, hands off |
| One shared credential set across all agents | Per-agent environments — each agent gets its own scoped credentials |
| Hard to move from demo to production | Human-in-the-loop by design — nothing merges without approval |

---

## What you can build

9 ready-made agent templates ship out of the box:

| Template | Trigger | What it does |
|----------|---------|-------------|
| **Autopilot Git → Slack** | GitHub issue label | Implements fix, opens PR, posts to Slack |
| **Dependency Updater** | Weekly cron | Bumps patch/minor deps, opens PR |
| **Incident Responder** | PagerDuty / OpsGenie webhook | Correlates commits, posts hypothesis to Slack |
| **Release Notes** | Git tag webhook | Reads merged PRs, writes CHANGELOG, posts to #releases |
| **Issue Triage** | GitHub issue.opened | Labels, prioritises, posts clarifying comment |
| **Deploy Monitor** | Vercel / Railway webhook | Monitors deployment, alerts on failure |
| **PR Review** | GitHub PR webhook | Reviews diff, posts structured feedback |
| **Scheduled Report** | Daily cron | Aggregates Linear issues, emails summary |
| **Custom Agent** | Any trigger | Build from scratch on the canvas |

---

## Block types

| Block | Purpose |
|-------|---------|
| **Trigger** | Starts a run — webhook, schedule, or manual |
| **Brain** | Agentic LLM step (Claude) with tool access and bounded autonomy |
| **Tool** | Deterministic integration call (GitHub, Slack, Linear, etc.) |
| **Logic** | Conditional branch — pass / fail paths |
| **Approval** | Pauses the run, sends a Slack DM with Approve / Reject buttons |
| **Output** | Sends a formatted summary via Slack, Email, or both |
| **Cleanup** | Always runs at the end — tear down sandboxes, close resources |

---

## Architecture

```
apps/
  web/          Next.js 14 — canvas UI, runs feed, settings
  api/          FastAPI + SQLAlchemy + Alembic
  api/worker.py Background run executor (Redis queue)
packages/
  conduct-cli/  Python CLI — run agents from the terminal or CI
```

**Infrastructure (local dev)**

```
postgres   pgvector/pgvector:pg16
redis      redis:7-alpine
api        FastAPI on :8000
worker     Run executor (same image, different entrypoint)
web        Next.js on :3000
```

---

## Getting started (UI)

### Prerequisites

- Docker + Docker Compose
- An Anthropic API key

### 1. Clone and configure

```bash
git clone https://github.com/sseshachala/delegator.git
cd delegator
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...
ENCRYPTION_KEY=<32-char random string>
```

### 2. Start all services

```bash
docker compose up -d
docker compose exec api alembic upgrade head
```

### 3. Open the app

- **UI**: http://localhost:3000
- **API docs**: http://localhost:8000/docs

### 4. Create your first agent

1. **Projects** → New project
2. **Agents** → New agent (or pick a template)
3. **Settings** → Environments → add GitHub + Slack credentials
4. Assign the environment to your agent from the canvas dropdown
5. Hit **Run**

---

## Getting started (CLI)

The `conduct` CLI lets you trigger agents from your terminal, CI pipeline, or scripts.

### Install

```bash
pip install conduct-cli
```

### Run an agent from a YAML file

```bash
conduct --server https://api.conductai.ai \
        --api-key YOUR_CLI_API_KEY \
        run autopilot.yaml
```

### YAML agent definition

```yaml
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
  body: "Tap on the submit button does nothing on iOS Safari."
```

### CLI flags

| Flag | Description |
|------|-------------|
| `--server` | Conduct API URL (e.g. `https://api.conductai.ai`) |
| `--api-key` | CLI API key — set `CLI_API_KEY` on the server |
| `--token` | Bearer token for Clerk auth (alternative to api-key) |
| `--workspace` | Workspace ID (overrides YAML `workspace_id`) |

---

## Integrations

Configure credentials in **Settings → Environments → [environment]**.
One credential per provider per environment. Need two GitHub accounts? Create two environments.

| Integration | Actions |
|-------------|---------|
| **GitHub** | create_repo, push_file, create_branch, open_pr, merge_pr, add_repo_secret |
| **Slack** | post_message, send_dm |
| **Linear** | fetch_issue, list_issues, create_issue, create_comment, update_issue_status |
| **Vercel** | list_deployments, get_deployment, wait_for_deployment, get_latest_deployment |
| **Railway** | trigger_deployment, list_services, get_deployment, wait_for_deployment |
| **DigitalOcean** | create_droplet, get_droplet, destroy_droplet, wait_for_droplet |
| **Email** | send_email (Resend or SendGrid) |

---

## Webhooks

| Endpoint | Service | Events |
|----------|---------|--------|
| `POST /webhooks/vercel` | Vercel | deployment.succeeded, deployment.ready, deployment.failed |
| `POST /webhooks/railway` | Railway | DEPLOY_SUCCESS, DEPLOY_FAILED, DEPLOY_CRASHED |
| `POST /webhooks/slack/interactions` | Slack | Approval button clicks |
| `POST /webhooks/inbound/{workflow_id}` | Generic | Any JSON payload |

---

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `ENCRYPTION_KEY` | Yes | 32-byte key for credential encryption |
| `DATABASE_URL` | Yes | Postgres connection string |
| `REDIS_URL` | Yes | Redis connection string |
| `API_BASE_URL` | Yes | Public URL of the API (for webhook callbacks) |
| `CLI_API_KEY` | Optional | Shared secret for CLI / CI access |
| `SLACK_SIGNING_SECRET` | Optional | Verifies Slack interactive component payloads |
| `RESEND_API_KEY` | Optional | Resend key for email output |
| `VERCEL_WEBHOOK_SECRET` | Optional | Verifies Vercel webhook signatures |
| `CLERK_SECRET_KEY` | Optional | Enables Clerk authentication |
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Optional | Clerk publishable key for the frontend |

---

## Deployment

### Render (API + worker)

1. New Web Service → connect GitHub → root directory: `apps/api`
2. Add a **PostgreSQL** database
3. Add a second service (same repo, root `apps/api`, start command: `python -m app.worker`)
4. Set environment variables
5. After first deploy: run `alembic upgrade head` via Render shell
6. Custom domain: add CNAME `api.conductai.ai → your-service.onrender.com`

### Vercel (frontend)

1. Connect GitHub repo → root directory: `apps/web`
2. Set `NEXT_PUBLIC_API_URL=https://api.conductai.ai`
3. Preview deployments automatically created for each PR

---

## License

MIT
