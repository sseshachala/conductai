# Delegator — Product Roadmap

> *Delegator is the AI layer on top of your existing engineering workflow — it picks up tickets, writes code, runs tests, and opens PRs, with a human approving before anything ships.*

---

## The Problem

Engineering teams are slow not because developers are slow — but because the gap between "ticket created" and "code in production" is filled with context switching, manual steps, and waiting.

- A ticket sits for days before someone picks it up
- A developer spends hours reading context before writing a line
- PRs wait for review while the author moves to the next task
- Deploys are manual, nerve-wracking, and undocumented

Delegator closes that gap. Not by replacing developers — by eliminating the mechanical work between intent and outcome.

---

## What Delegator Does

A developer labels a GitHub issue `autopilot ready`.

Delegator:
1. Reads the issue
2. Clones the repo, understands the codebase
3. Writes the fix
4. Runs the tests — fixes failures automatically (up to 3 attempts)
5. Opens a pull request with a clear description
6. Notifies the developer on Slack
7. Waits for human approval before anything merges

The developer reviews the PR. One click. Done.

**Same day. Zero context switching. Human still in control.**

---

## Who It's For

Engineering teams of 5–50 who:
- Use GitHub + Slack (or Linear) already
- Ship features on a weekly cadence
- Want to move faster without hiring more engineers
- Need auditability — they can't have a black box touching production

---

## What We Are Not

- Not a no-code tool for non-engineers
- Not an AI chatbot
- Not an agent platform (infrastructure)
- Not a replacement for developers
- Not competing with LangChain, Temporal, or Google Agentspace on runtime infrastructure

We sit **on top** of your existing tools. We don't replace them.

---

## Roadmap

### Phase 1 — Core SDLC Loop ✅ Done

The end-to-end path from ticket to PR, running locally.

- Visual canvas: drag-and-drop workflow builder
- DAG executor with background worker
- GitHub integration: fetch issue, clone, branch, push, open PR
- Slack integration: post message, DM, approval buttons
- Brain block: agentic Claude loop with file/shell/search tools
- Logic block: branch on test pass/fail
- Approval block: pause, notify, resume on human decision
- Run trace: live SSE stream, full event log
- Dry Run: simulate without touching real systems
- Credential vault: encrypted per workspace
- Autopilot workflow seeded: label issue → Brain implements → tests → PR → Slack notify

---

### Phase 2 — Reliability & Trust ← Now

The thing that makes teams actually let it touch production.

**Parameterized runs**
- Define input schema per workflow (repo, branch, issue number, etc.)
- Pre-run form in UI — fill params before triggering
- Webhook payloads auto-map to params
- Block configs reference `{{params.repo}}` — same canvas, different inputs

**Better test handling**
- Detect test runner automatically (pytest, jest, npm test, go test)
- Parse test output — show which tests failed and why in the trace
- Fix loop improvements: Brain sees structured failure, not raw output

**Smarter Brain prompts**
- Auto-inject repo context: language, framework, folder structure
- Brain reads existing tests before writing code — matches style
- Brain writes a test for every change it makes

**Trace improvements**
- Show token count + estimated cost per run
- Show which files were changed in the Brain block output
- Link directly to the opened PR from the trace

---

### Phase 3 — Pre-built Workflow Library

Teams shouldn't have to build from scratch. Ship ready-to-use workflows for the most common SDLC tasks.

| Workflow | Trigger | What it does |
|----------|---------|-------------|
| **Autopilot** | Issue labeled `autopilot ready` | Implement fix, run tests, open PR |
| **Test generator** | Issue labeled `add tests` | Read code, write missing tests, open PR |
| **Dependency upgrade** | Weekly schedule | Bump deps, run tests, open PR if green |
| **Incident responder** | PagerDuty / Slack alert | Read logs, identify root cause, post summary, open fix PR |
| **PR reviewer** | PR opened | Read diff, post review comments on GitHub |
| **Release notes** | Tag pushed | Read merged PRs since last tag, write release notes, post to Slack |

Each workflow:
- One-click install into your workspace
- Works with GitHub + Slack out of the box
- Fully editable on the canvas after install

---

### Phase 4 — Connects to Where Teams Live

Expand the integration surface so Delegator fits into any engineering team's existing stack without asking them to change tools.

**Ticket sources (triggers)**
- Linear — label `autopilot ready`
- Jira — transition to `In Progress (AI)`
- GitHub Issues — already done ✓

**Notification targets**
- Slack — already done ✓
- Email — already done ✓
- Microsoft Teams
- GitHub PR comments (Brain posts its own progress updates)

**CI/CD awareness**
- Read GitHub Actions results — Brain sees test output from CI, not just local
- Trigger on CI failure — workflow fires when a build breaks
- Post deploy status back to the originating Slack thread

---

### Phase 5 — Governance & Auditability

What enterprises need before they allow agents near production.

**Per-workflow policies**
- Tool allowlist — define exactly which integrations an agent may use
- Max lines changed per run — reject PRs over a threshold
- Forbidden file paths — agent cannot touch `.env`, `secrets/`, migrations
- Budget caps — max LLM spend and max wall time per run

**Audit log**
- Every external API call logged with timestamp, params, response hash
- Immutable — cannot be edited or deleted
- Exportable to CSV / shipped to your SIEM

**Agent Registry**
- Catalog of all workflows in the workspace
- Version history with diff view
- Clone a workflow as a template

---

### Phase 6 — Scale & Self-Hosted

For larger teams and enterprises who need to run Delegator in their own infrastructure.

- Docker Compose production bundle (single command deploy)
- Helm chart for Kubernetes
- Bring-your-own LLM — OpenAI, Mistral, local Ollama (not just Claude)
- SSO via SAML / OIDC
- Per-team workspaces with RBAC

---

## The Metric That Matters

**Time from ticket to merged PR.**

Everything on this roadmap either reduces that number or makes teams trust the process enough to let it run. If a feature doesn't do one of those two things, it's not on the roadmap.

---

## Current Status

| Capability | Status |
|-----------|--------|
| Autopilot: issue → Brain → tests → PR | ✅ Live |
| Canvas workflow builder | ✅ Live |
| GitHub, Slack, Linear, Vercel, Railway, DO, Email | ✅ Live |
| Approval gates | ✅ Live |
| Dry Run mode | ✅ Live |
| Webhook triggers (GitHub, Vercel, Railway) | ✅ Live |
| Run trace (live + history) | ✅ Live |
| Parameterized runs | 🔲 Phase 2 |
| Pre-built workflow library | 🔲 Phase 3 |
| Jira / Teams / CI integration | 🔲 Phase 4 |
| Governance & audit log | 🔲 Phase 5 |
| Self-hosted / RBAC | 🔲 Phase 6 |

---

## Deployment (Pending)

- **Backend + worker**: Railway — `sseshachala/delegator`, root `apps/api`
- **Database**: Railway Postgres plugin
- **Frontend**: Vercel — `sseshachala/delegator`, root `apps/web`
- **GitHub webhook**: `POST https://<railway-url>/webhooks/github` → Issues events
