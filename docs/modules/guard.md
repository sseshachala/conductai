# ConductGuard — AI Tool Fleet Management for Engineering Teams
**v0.3 · May 2026**

---

## The Core Idea

**Manager configures. Everything pushes down. Developers just work.**

Think MDM (Mobile Device Management) for laptops — but for AI coding tools. The IT/security team sets policies on a laptop fleet once, and every laptop gets it automatically. Developers don't configure their own security. It just works.

ConductGuard is that system for Claude Code, Codex, Cursor, and Gemini CLI.

---

## The Problem

A team of 6 developers is running AI coding sessions all day. The team lead has:
- No visibility into what the AI is doing
- No way to set limits or standards across the team
- No idea what it's costing
- No audit trail if something goes wrong
- No way to push best practices without emailing everyone

Every developer is running their own mental model of what's acceptable. Some use RTK for token savings, some don't. Some have guardrails, most don't. The team lead finds out about problems after the fact — a force push to main, a hardcoded secret, a $400 API bill.

---

## How It Works

### Direction of control

```
MANAGER / TEAM LEAD
(ConductGuard Dashboard)
        │
        │  Push down:
        │  ├── Policies (block / warn / approve / audit rules)
        │  ├── Token optimizer config (which filters, which tools)
        │  ├── Spend budgets (per developer, per project)
        │  ├── Approved AI tools (Claude only? Codex too?)
        │  └── Best practice injections (what reminders to add)
        │
        ▼
Every developer's machine (auto-synced, no developer action needed)
        │
        │  Report up:
        │  ├── All AI agent actions (what, who, when)
        │  ├── Token usage and spend (actual vs. optimized)
        │  ├── Policy violations
        │  └── Risk events
        │
        ▼
MANAGER / TEAM LEAD
(Dashboard: full picture, real-time)
```

Config goes down. Telemetry goes up. Developer is in the middle, working normally.

### Developer experience: zero config

```bash
# Team lead sends invite link. Developer runs one command:
conductguard join <team-invite-code>

# That's it. Everything else is managed by the team lead.
# Claude Code, Codex, Cursor — all covered automatically.
# Developer works exactly as before. Governance + optimization just happens.
```

No YAML to write. No rules to configure. No RTK to install separately. The team lead decides what everyone gets.

---

## What the Manager Controls

### 1. Token Optimizer

The manager decides which optimizations apply to the team. Developers get them automatically.

```
Dashboard → Optimize → Rules

[ ✓ ] git commands           compact format          saves ~70%
[ ✓ ] test output            failures only           saves ~90%
[ ✓ ] build output           errors grouped          saves ~80%
[ ✓ ] file reads             noise filtered          saves ~60%
[ ✓ ] docker / kubectl       deduplicated logs       saves ~85%
[   ] network responses      compact HTTP            saves ~70%

Estimated team savings this month: $1,240  (from $1,800 → $560)
```

Enable once → applies to every developer's session automatically.

### 2. Policies

Write rules in the dashboard. They propagate to the whole team within 60 seconds.

```
Dashboard → Policies → Add Rule

Rule: no-force-push
  Match: bash commands matching "git push --force"
  Action: Block
  Message: "Force push blocked. Open a PR."
  Applied to: All developers  ✓

Rule: approve-prod-deploy
  Match: bash commands matching "deploy.*production"
  Action: Require approval
  Via: Slack → #engineering
  Applied to: All developers  ✓

Rule: audit-migrations
  Match: file edits matching alembic/versions/*.py
  Action: Audit silently
  Applied to: All developers  ✓
```

Policy library: 20 built-in rules the manager can enable with one click. Custom rules always available.

### 3. Spend Budgets

```
Dashboard → Spend → Budgets

Monthly budget per developer:  $150
  Alert at:    80%  →  notify developer + team lead via Slack
  Hard limit:  100% →  block new AI sessions until next month

Per-project budget:  [configure per repo]

Current month:
  alice      $42 / $150   ▓▓▓░░░░░░░░  28%
  bob        $118 / $150  ▓▓▓▓▓▓▓▓░░░  79%  ⚠ approaching limit
  carol      $31 / $150   ▓▓░░░░░░░░░  21%
  sudhi      $67 / $150   ▓▓▓▓░░░░░░░  45%
```

### 4. Approved AI Tools

```
Dashboard → Tools → Allowed Tools

[ ✓ ] Claude Code      (Anthropic)
[ ✓ ] Codex            (OpenAI)
[   ] Cursor           (blocked — not reviewed yet)
[   ] Gemini CLI       (blocked — pending security review)

If a developer uses a blocked tool, ConductGuard logs it and notifies the team lead.
```

### 5. Best Practice Injections

Reminders pushed into agent context at the right moment — without the developer having to remember.

```
Dashboard → Injections → Add

Trigger: agent edits a migration file
Inject:  "This is a database migration. Ensure downgrade() is implemented and tested."

Trigger: agent runs git commit
Inject:  "Run the test suite before committing. Use: pytest / npm test"

Trigger: agent edits a file in /apps/api/app/core/
Inject:  "Core module — changes here affect all workspaces. Test thoroughly."
```

The developer's AI sees these reminders at exactly the right moment. Better outcomes, no extra effort from the developer.

---

## Team Dashboard

### Real-Time Activity Feed

```
14:32  sudhi    Claude Code   edited   apps/api/app/routers/auth.py
14:31  alice    Codex         bash     pytest tests/ → 3 failures (output optimized: 91% saved)
14:30  bob      Claude Code   bash     git push --force origin main  🚫 blocked: no-force-push
14:28  sudhi    Claude Code   bash     alembic upgrade head  🔒 approval: pending
14:25  alice    Codex         edited   alembic/versions/0035.py  📋 audited
```

### Spend Overview

```
This month: $258 / $900 team budget (29%)
Saved by optimizer: $1,240 (vs. unoptimized)

By developer:  [bar chart]
By project:    [bar chart]
By AI tool:    Claude 78%  ·  Codex 22%
By day:        [trend line]
```

### Violations & Risk Events

All blocked, warned, and approval-gated actions across the team. Assignable, resolvable.

### Audit Trail

Every AI agent action, immutable, exportable. Date range → JSON/CSV for SOC 2 evidence.

---

## Conduct Integration

When a Conduct agent run starts, ConductGuard governance and optimization apply automatically — no extra config in the playbook.

```
Conduct run starts
  → ConductGuard middleware loads team policy (same policy as developer sessions)
  → Every tool call the agent makes: policy-checked + output optimized
  → Violations: halt run or gate on approval (Slack)
  → Run ends: full action log in Conduct observability
  → Cost shown as: actual vs. optimized
```

The manager sees Conduct agent runs in the same ConductGuard dashboard as developer sessions. One view for all AI activity — human-driven or automated.

---

## Onboarding Flow

### For the team lead (5 minutes)

```
1. Sign up at conductguard.conductai.ai
2. Create team → get invite code
3. Configure: enable optimizer rules, turn on default policies
4. Share invite code with team
```

### For each developer (60 seconds)

```bash
conductguard join abc-xyz-123      # invite code from team lead
# → installs hooks for Claude Code, Codex, Cursor
# → downloads current team policy
# → done
```

From that point: policy updates, optimizer changes, budget changes — all push down automatically. Developer never touches ConductGuard again unless they want to check their own spend.

---

## Policy Propagation

```
Manager changes a rule in dashboard
        ↓ (within 60 seconds)
ConductGuard hook on every developer machine polls for config update
        ↓
New policy active on all sessions
        ↓
Manager sees confirmation: "Policy pushed to 6/6 developers"
```

No restarts. No developer action. No Slack message asking people to update.

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Hook binary | Rust | Single binary, no runtime — installs in seconds, same RTK pattern |
| Token optimizer | Built into hook binary | Same intercept point — one binary does optimize + enforce |
| Config sync | Polling (60s interval) or webhook push | Simple, reliable, no persistent connection needed |
| Backend | FastAPI | Reuse Conduct stack for event ingestion, policy storage, team management |
| Dashboard | Next.js | Reuse Conduct component library |
| Audit storage | Postgres | Shared with Conduct in embedded mode |
| Realtime feed | SSE | Same pattern as Conduct observability |

---

## Build Phases

### Phase 1 — Hook Binary (3 weeks)
- Rust binary: policy check (PreToolUse) + token optimizer (PostToolUse)
- Config pulled from backend on session start + polled every 60s
- Local cache so sessions work offline
- `conductguard join <code>` onboarding

**Exit criteria:** Team lead changes a policy in dashboard → propagates to developer hook within 60 seconds.

### Phase 2 — Manager Dashboard (3 weeks)
- Team creation + invite codes
- Policy editor (built-in library + custom rules)
- Optimizer toggle panel
- Real-time activity feed
- Spend by developer

**Exit criteria:** Team lead can see all 3 developers' Claude sessions in one dashboard without touching their machines.

### Phase 3 — Spend Controls + Budgets (2 weeks)
- Monthly budget per developer
- Alert at threshold (Slack + email)
- Hard limit enforcement
- Spend trends and projections

**Exit criteria:** Developer hits 80% budget → Slack alert fires to team lead and developer.

### Phase 4 — Conduct Integration (2 weeks)
- ConductGuard middleware in Conduct agent runs
- Same policy applied to automated runs
- Conduct runs appear in ConductGuard dashboard alongside developer sessions

**Exit criteria:** Manager sees Conduct agent run and developer sessions in one unified activity feed.

### Phase 5 — Compliance + Enterprise (4 weeks)
- Audit export (SOC 2 format)
- Approved tools enforcement
- Best practice injection panel
- Self-hosted option (Docker Compose)
- SAML/SSO for enterprise

---

## What's Different From v0.2

| v0.2 | v0.3 |
|---|---|
| Developer installs and configures | Manager configures, developer just joins |
| Data flows up | Config pushes down AND data flows up |
| Policy as YAML in repo | Policy in dashboard, synced automatically |
| RTK as separate add-on | Optimizer built in, manager-controlled |
| Control plane framing | Fleet management framing |

The shift: **the buyer and operator is the team lead, not the developer.** The developer is the beneficiary — better guardrails, automatic optimization — but they don't drive adoption and they don't configure anything.

---

## Positioning

**"Mobile Device Management for AI coding tools."**

Your IT team manages your laptop fleet. Nobody expects each developer to configure their own security policy. ConductGuard does the same for Claude Code and Codex — the team lead is in control, developers just work.

---

*v0.3 · May 2026 · Houston*
