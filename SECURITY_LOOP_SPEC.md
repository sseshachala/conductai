# Conduct Security Loop
**v0.3 · June 6, 2026**

---

## TL;DR

AI coding tools — Claude Code, Codex CLI, Cursor, GitHub Copilot — surface security findings constantly. None of them close the loop. They stop at "here's a finding." Conduct is the response layer: it captures findings from any AI tool, routes them through a standardized triage → fix → PR pipeline, and gives security and engineering teams a single audit trail across every tool they run.

**The claim:** Connect your AI coding tools to Conduct once. Every security issue they find automatically gets triaged, fixed, and shipped as a PR — with a full audit trail.

---

## 1. The Problem

Engineering teams in 2026 run 2–4 AI coding tools simultaneously. Each tool surfaces security findings differently:

- Claude Code prints to terminal, fires hooks
- Codex CLI outputs findings inline, has a hook system
- Cursor shows inline suggestions with no external routing
- GitHub Copilot posts PR comments

**Nothing connects these findings to action.** A finding surfaced at 2pm on a Thursday:
- May or may not become a GitHub issue
- May or may not get triaged for severity
- May or may not get fixed before the next release
- Definitely has no audit trail linking detection → remediation

For security teams, this is a compliance gap. For engineering managers, it's invisible risk. For CTOs, it's indefensible in a security review.

---

## 2. The Solution

Conduct sits between AI coding tools and your repo/issue tracker as the **security response layer**.

```
AI tool surfaces finding
        ↓
Conduct captures it (Guard hook / MCP event / webhook)
        ↓
GitHub issue created with severity + labels
        ↓
Security scanner validates the finding
        ↓
AI applies the fix on a branch
        ↓
PR opened back to the repo
        ↓
Slack notification → #security
        ↓
Full run trace: tool → finding → fix → PR → cost → duration
```

Every step is traceable. Every finding has a run ID. Nothing falls through.

---

## 3. Finding Schema

Standardized shape for a security finding entering Conduct from any source:

```json
{
  "tool": "claude-code | codex | cursor | copilot | manual",
  "severity": "critical | high | medium | low | info",
  "type": "injection | path-traversal | secret-leak | auth-bypass | crypto | other",
  "file": "scripts/cbh.py",
  "line": 107,
  "description": "TLS verification disabled via ssl.CERT_NONE without warning",
  "suggested_fix": "Add warning comment and runtime print when proxy mode is active",
  "repo_full_name": "owner/repo",
  "commit_sha": "abc1234",
  "source_run_id": "optional — if surfaced inside a Conduct run"
}
```

This becomes the `_trigger` shape for the Security Loop pipeline.

---

## 4. Pipeline Blocks

| Step | Block type | Playbook | Status |
|---|---|---|---|
| Capture finding | Webhook / Guard hook / MCP | — | needs emitter per tool |
| Create GitHub issue | Tool — github/create_issue | issue-triage | exists |
| Triage + label | Brain | issue-triage | exists |
| Validate finding | Brain | security-scanner | exists |
| Apply fix | Brain | thirdparty-autopilot-fix | exists |
| Open PR | Tool — github/open_pull_request | thirdparty-autopilot-fix | exists |
| Notify Slack | Output | all playbooks | exists |
| Audit trace | Run feed | platform | exists |

**Most of the pipeline is already built.** The missing pieces are narrow.

---

## 5. What's Already Built

- **ConductGuard** — already hooked into Claude Code and Codex CLI, intercepts every tool call. Natural place to emit security findings.
- **security-scanner playbook** — validates findings, produces structured severity output
- **thirdparty-autopilot-fix playbook** — forks any third-party repo, applies fix, opens PR
- **issue-triage playbook** — creates and labels GitHub issues
- **Webhook ingestion** — Conduct already accepts GitHub webhooks; same infra handles tool events
- **Run trace** — every pipeline execution is fully traced with cost, turns, duration, tool output

---

## 6. What's New (Build List)

### 6a. Two-track emitter strategy

There are two complementary approaches to capturing findings. Both ship — A first (low effort, immediate coverage), B second (universal coverage). They are not alternatives; they are layers.

**Track A — Extend ConductGuard (Claude Code + Codex CLI)**

ConductGuard is already registered inside Claude Code and Codex CLI and intercepts every tool call. We add a second responsibility: a **finding classifier** that inspects each tool call output and, when it looks like a security finding, emits a structured event to Conduct.

```
Tool call completes
        ↓
Guard PostToolUse hook fires (already exists)
        ↓
Finding classifier runs (new) — LLM call or regex heuristic
        ↓
If finding detected → POST to Conduct webhook
        ↓
Security Loop pipeline starts
```

The classifier is the core new piece. It needs to answer: "does this output contain a security vulnerability worth acting on?" Options:
- **Fast path:** regex + keyword matching (secret patterns, OWASP terms, CVE refs) — zero latency, zero cost
- **Slow path:** lightweight LLM call (Haiku) to classify ambiguous output — only fires when fast path is uncertain

Dependency: classifier must exist before Track A emitter can ship.

| Tool | Mechanism | Dependency | Effort |
|---|---|---|---|
| Claude Code | `PostToolUse` hook in Guard (already wired) | Classifier | Low |
| Codex CLI | `after_tool` hook in Guard (already wired) | Classifier | Low |

**Track B — Universal Webhook Bridge (all other tools)**

A thin HTTP bridge that any tool can call — structured or unstructured. For tools with no hook system, Conduct provides a webhook endpoint that accepts raw text and runs the classifier server-side.

| Tool | Mechanism | Dependency | Effort |
|---|---|---|---|
| GitHub Copilot | PR comment webhook → Conduct | Webhook endpoint (exists) | Low |
| Cursor | `.cursor/rules` file + background script | Webhook endpoint | Medium |
| Claude-BugHunter | Output pipe → `conduct emit finding` CLI command | CLI emit command | Low |
| codexstar69/bug-hunter | Same — pipe output to CLI | CLI emit command | Low |
| Any tool | `conduct emit finding --text "..."` from terminal | CLI emit command | Low |

Track B also ships a CLI command `conduct emit finding` that any tool or script can call directly:

```bash
# Pipe any tool output into Conduct
claude-bughunter scan | conduct emit finding --repo owner/repo --tool claude-bughunter
codex run hunt.sh | conduct emit finding --repo owner/repo --tool codex
```

This makes it universal — if a tool produces text output, it can feed into the Security Loop with one pipe.

**Dependency map:**

```
Classifier (fast + slow path)
    ├── Track A — Guard emitter (Claude Code, Codex)        [Week 1-2]
    └── Track B — Webhook bridge + CLI emit command         [Week 3-4]
            ├── Copilot PR webhook
            ├── Claude-BugHunter pipe
            ├── codexstar69/bug-hunter pipe
            └── Cursor rules integration                    [Week 5-6]
```

### 6b. `security_finding` trigger shape

New trigger shape in `input_contract.py` alongside `_trigger`, `github`, and `manual`:

```python
# security_finding shape
{
  "security_finding": {
    "tool": "...",
    "severity": "...",
    "type": "...",
    "file": "...",
    "description": "..."
  }
}
```

### 6c. Security Loop playbook

A new orchestration playbook that wires the full pipeline together as a single installable agent:

```yaml
name: Security Loop
on:
  webhook:
    trigger: security_finding
    next: create_issue

blocks:
  create_issue → triage → validate → implement_fix → open_pr → notify_slack
```

### 6d. Dashboard view — Security Loop feed

Dedicated view in the Conduct console showing:
- All security findings captured (across all tools)
- Status per finding: detected / triaged / fixing / PR open / merged / dismissed
- Tool breakdown: how many findings per tool
- Mean time to fix (MTTF)

---

## 7. Integration Targets (Phase 1)

| Tool | Market share | Integration path |
|---|---|---|
| Claude Code | Growing fast | ConductGuard hook — already wired |
| Codex CLI | OpenAI user base | `after_tool` hook in codex.toml |
| GitHub Copilot | Largest install base | PR comment → webhook |
| Cursor | Strong among indie devs | Cursor rules + background agent |

---

## 8. What We Can Claim

1. **Zero-drop security** — every finding from every AI tool enters the same pipeline. Nothing gets lost in a terminal output.
2. **Tool-agnostic** — one Conduct workspace handles Claude Code, Codex, Cursor, Copilot. Same pipeline, same trace.
3. **Autonomous remediation** — finding → PR in minutes, not days.
4. **Audit trail** — every finding has a traceable run: detected by which tool, triaged by which playbook, fixed by which agent, approved by whom, PR URL, cost, duration.
5. **Compliance evidence** — exportable run traces showing vulnerabilities were detected and remediated, with timestamps and approvals.

---

## 9. Target Buyer

**Primary:** Engineering orgs (50–500 engineers) running multiple AI coding tools with no unified security response process.

**Secondary:** Security teams at those orgs who need evidence that AI-surfaced findings were acted on — for SOC 2, internal audits, or board-level security reviews.

**Champion:** Engineering manager or security lead who is already using Claude Code or Codex and is uncomfortable that findings disappear into terminal output.

---

## 10. Success Metrics (6 months)

| Metric | Target |
|---|---|
| Tools connected per workspace | ≥ 2 |
| Findings captured per active workspace / week | ≥ 5 |
| % findings that reach PR stage | ≥ 60% |
| Mean time to fix (MTTF) | < 30 minutes |
| Workspaces with Security Loop installed | 20 |

---

## 11. Build Sequence

**Week 1–2** — Foundation
- `security_finding` trigger shape in `input_contract.py`
- Finding classifier (fast path: regex + keywords)
- Track A: Guard emitter for Claude Code (PostToolUse hook)
- Security Loop playbook YAML

**Week 3–4** — Track A complete + Track B starts
- Track A: Guard emitter for Codex CLI (`after_tool` hook)
- Finding classifier slow path (Haiku LLM call for ambiguous output)
- `conduct emit finding` CLI command (Track B foundation)
- `create_issue` action in GitHub integration
- End-to-end smoke test: Claude Code finding → PR in one run

**Week 5–6** — Track B expands
- Copilot PR comment → Conduct webhook path
- Claude-BugHunter + codexstar69/bug-hunter pipe support
- Dashboard Security Loop feed (findings status view)
- Export / compliance report

**Week 7–8** — Coverage complete
- Cursor rules integration
- MTTF metric in dashboard
- Launch blog post + demo video

---

## 12. Open Questions

1. Should dismissed findings (false positives) be tracked separately in the dashboard?
2. Do we want human approval gates before the fix branch is pushed? (autopilot-approved pattern)
3. Classifier accuracy threshold — what confidence level triggers an emit vs. silent discard?
4. Severity threshold — should low/info findings auto-close without creating an issue?
5. For Track B `conduct emit finding` — should the CLI block until the pipeline completes, or fire-and-forget?

---

---

## 13. Detailed Flow & Use Case

### End-to-end flow

```
1. Developer runs Claude-BugHunter or codexstar69/bug-hunter in terminal
        ↓
2. Security Loop CLI extension (built into ConductGuard)
   - For Claude-BugHunter: structured markdown output → parsed directly
   - For Codex bug-hunter: raw unstructured terminal output → classifier normalizes it
        ↓
3. Classifier produces standardized finding schema
   { tool, severity, type, file, line, description, suggested_fix, repo_full_name }
        ↓
4. ConductGuard CLI sends finding to new Conduct API endpoint
   POST /security-findings  { workspace_id, finding }
        ↓
5. API stores finding in DB, triggers SSE refresh to console
        ↓
6. /security console page surfaces the finding in real-time
        ↓
7. GitHub issue auto-created in the target repo
   - Title: "[severity] finding-type in file" 
   - Body: description + suggested fix + tool source
   - Labels: security, severity-high (etc.)
        ↓
8. issue-triage playbook fires automatically
   - Classifies type and priority
   - Adds labels
   - Posts clarifying comment if description is thin
        ↓
9. Draft Agent auto-created in "Security" project
   - Template: thirdparty-autopilot-fix
   - Pre-filled: upstream_owner, upstream_repo, issue_number (from step 7)
   - Status: draft — does NOT run automatically
        ↓
10. Slack notification → #security channel
    "🐛 [HIGH] path-traversal in owner/repo — issue #N created, draft agent ready → [View in Conduct]"
        ↓
11. Security engineer reviews finding + draft agent in /security console
    Approves → clicks Run
        ↓
12. security-scanner playbook validates the finding
        ↓
13. thirdparty-autopilot-fix fires
    fork → clone → fix → push branch → open PR
        ↓
14. Slack notification → #security
    "✅ PR opened: fix/issue-N in owner/repo → [PR link]"
        ↓
15. Full run trace in Conduct dashboard
    tool → finding → issue → triage → fix → PR → cost → duration
```

### Component breakdown

**A. ConductGuard CLI extension**

Two modes depending on the source tool:

- **Claude-BugHunter mode:** CBH outputs structured markdown with findings. Guard parses this directly — no classifier needed. Key fields map cleanly: severity, file, description, suggested fix.

- **Codex bug-hunter mode:** Raw terminal output, unstructured. Guard pipes this through the classifier before emitting. Classifier uses fast path (regex: CVE refs, OWASP terms, secret patterns) + slow path (Haiku LLM call) for ambiguous output.

Usage:
```bash
# Pipe claude-bughunter output into Guard
cbh scan --target acme | conductguard emit --tool claude-bughunter --repo owner/repo

# Pipe codex bug-hunter output into Guard
codex run hunt.sh | conductguard emit --tool codex-bughunter --repo owner/repo
```

**B. Classifier (Codex + unstructured tools)**

Input: raw terminal text
Output: standardized finding schema or null (if no finding detected)

Fast path — regex patterns:
- Secret leak: `(api_key|secret|password|token)\s*=\s*["\'][^"\']{8,}`
- Path traversal: `path traversal|directory traversal|REPO_ROOT`
- Injection: `sql injection|command injection|shell injection|XSS`
- CVE reference: `CVE-\d{4}-\d+`
- OWASP class: `OWASP [AT]\d+`

Slow path — Haiku call when fast path confidence is low:
```
"Does the following output describe a security vulnerability? 
If yes, return JSON with: severity, type, file, description, suggested_fix. 
If no, return null."
```

**C. API endpoint**

```
POST /security-findings
Headers: x-api-key or Authorization
Body: {
  tool: string,
  severity: critical|high|medium|low|info,
  type: string,
  file: string,
  line: number,
  description: string,
  suggested_fix: string,
  repo_full_name: string,
  commit_sha: string,
  raw_output: string  // original text for audit
}

Response: { finding_id, agent_id, slack_ts }
```

DB: new `security_findings` table — finding_id, workspace_id, tool, severity, status, finding payload, agent_id (FK to workflows), created_at.

SSE: existing run-feed SSE infrastructure reused to push finding updates to `/security` page.

**D. /security console page**

Real-time feed of all captured findings across all tools:

| Column | Value |
|---|---|
| Severity | critical / high / medium / low badge |
| Type | injection / path-traversal / secret-leak etc. |
| Repo | owner/repo |
| Tool | claude-bughunter / codex / cursor |
| Status | captured → draft → running → PR open → merged |
| Agent | link to the auto-created draft agent |
| Time | when captured |

**E. Issue creation + triage**

Immediately after a finding is stored:
1. `github/create_issue` action fires — creates issue in the target repo with severity label and structured body
2. `issue-triage` playbook fires on the new issue — classifies, labels, posts comment
3. Issue number returned and stored against the finding record

**F. Auto-create draft Agent**

After issue is created and triaged:
1. Look up or create a "Security" project in the workspace
2. Instantiate `thirdparty-autopilot-fix` template as a new agent
3. Pre-fill inputs: `upstream_owner`, `upstream_repo`, `issue_number` (from step E)
4. Set agent status to `draft` — does NOT run automatically
5. Link agent ID back to the finding record

The engineer reviews the draft in the console and clicks Run when ready. This keeps humans in the loop before any code is changed.

The draft agent Run fires: security-scanner → thirdparty-autopilot-fix → PR opened.

**F. Slack notification**

Fires immediately on finding capture, before the agent runs:

```
🐛 New security finding — [HIGH] path-traversal in elementalsouls/Claude-BugHunter
Tool: claude-bughunter  |  File: scripts/cbh.py
Draft agent ready in Security project → [View in Conduct]
```

---

## 14. Architecture (Revised)

```
Claude Code / Codex CLI
        ↓
Security Loop CLI  ← new tool; wraps both, classifies output, emits findings
        ↓
ConductGuard  ← already hooked in; routes the event to Conduct API
        ↓
/security console page  ← findings feed inside Conduct dashboard
```

**Three things to build:**

1. **`/tools/security-loop`** — module page on conductai.ai (same pattern as `/tools/agent-booster`)
2. **`/security` console page** — findings feed inside the Conduct app (captured findings, status per finding, MTTF, tool breakdown)
3. **Security Loop CLI** — standalone tool package that wraps Claude Code + Codex CLI, runs the finding classifier, and emits structured events to ConductGuard

**`/tools` page** gets a third card (Security Loop, Early Access) linking to `/tools/security-loop`.

---

## 15. Build vs Reuse Map

### Already exists on Conduct — use as-is

| What | Where |
|---|---|
| `issue-triage` playbook | fires on new GitHub issue → labels + triage |
| `security-scanner` playbook | validates a finding |
| `thirdparty-autopilot-fix` playbook | fork → clone → fix → PR |
| `github/open_pull_request` action | open PR tool block |
| Slack output block | notifications |
| Webhook ingestion | already accepts external events |
| Run trace + SSE | full audit trail, real-time console updates |
| ConductGuard hooks | already wired inside Claude Code + Codex CLI |
| Credential vault + environments | auth for GitHub, Slack |
| `fork_repo` action (all 3 fork cases) | generic fork handling |
| `thirdparty-autopilot-fix` playbook | end-to-end fix pipeline |

### Needs to be built — new

| What | Layer | Effort |
|---|---|---|
| `github/create_issue` action | API — `github.py` | Small |
| `POST /security-findings` endpoint | API — new router | Medium |
| `security_findings` DB table + model | API — DB + migration | Small |
| Draft agent auto-creation on finding ingest | API — business logic | Medium |
| `security_finding` trigger shape | API — `input_contract.py` | Small |
| Security Loop playbook YAML | Playbook | Small |
| `/security` console page | Frontend | Medium |
| Finding classifier — fast path (regex) | Guard CLI — Python | Small |
| Finding classifier — slow path (Haiku) | Guard CLI — Python | Medium |
| `conductguard emit` CLI command | Guard CLI | Small |
| CBH structured output parser | Guard CLI | Small |
| Codex raw output → classifier pipe | Guard CLI | Medium |
| `/tools/security-loop` module page | Marketing site | Small |
| Tools page — Security Loop card | Marketing site | Small |

### Critical path (what blocks what)

```
github/create_issue action (github.py)
        ↓
POST /security-findings endpoint + DB table
        ↓
draft agent auto-creation logic (API)
        ↓
/security console page (Frontend)

— parallel track —

conductguard emit CLI command
        ↓
classifier fast path (regex)
        ↓
classifier slow path (Haiku)
        ↓
CBH parser + Codex pipe
```

Everything downstream of `POST /security-findings` can be built in parallel once the endpoint and DB table exist. The classifier and CLI emit command are independent of the API work and can be built simultaneously.

---

## 16. Run Trigger Modes

### The safety boundary — always PR, never merge

Regardless of draft or autopilot mode, **the agent never merges code**. It stops at opening a PR. The merge is always a human decision.

```
Agent does:                          Human does:
  classify finding                     review PR diff
  validate (security-scanner)          run / wait for CI
  fork → clone → fix                   request changes if needed
  push branch                          merge when satisfied
  open PR  ← agent stops here  →      merge  ← always manual
```

This means even autopilot is safe — worst case is a PR with a bad fix that gets rejected. Nothing ships to main without a human merge.

**Risk model:**

| Step | Risk | Mitigation |
|---|---|---|
| Finding classification | False positive | security-scanner validates before fix runs |
| Fix quality | Wrong or incomplete fix | PR review + CI catches it before merge |
| PR target branch | Wrong base branch | `fork_upstream.default_branch` used |
| Merge | Bad code ships | Always manual — agent never merges |

### Phase 1 — Draft mode (build first)

Finding lands → draft agent created in Security project → human reviews finding → clicks Run (UI or CLI) → agent runs → PR opened.

Human approves *before* the agent runs. Default for all workspaces.

```
finding captured → draft agent → human clicks Run → fix → PR opened → human merges
```

### Phase 2 — Autopilot mode (future workspace setting)

Finding lands → agent runs immediately if severity meets threshold → PR opened → human merges.

Human approves *after* — by reviewing and merging the PR. No approval needed to start the run.

```
finding captured → agent runs immediately → PR opened → human merges
```

| Severity | Default autopilot behaviour |
|---|---|
| critical | auto-run immediately |
| high | auto-run immediately |
| medium | draft — human approves run |
| low / info | draft — or auto-close |

Controlled by a workspace setting: **Security Loop run mode** — `draft` (default) or `autopilot`.

### Trigger surfaces (both modes)

| Surface | How |
|---|---|
| Conduct console | Click Run on draft agent in /security page |
| CLI | `conduct run <agent-name> --project Security` |
| Autopilot | Fires automatically on finding ingest — no human action needed |

---

---

## 17. Multi-Agent Chain — The Bigger Picture

Security Loop is not a single playbook. It is a **chain of specialized agents** that work in tandem, each doing one thing well and handing state to the next.

```
Security Loop CLI  (emitter — wraps Claude Code / Codex)
        ↓ finding event
Security Findings Agent  (capture + store + create GitHub issue)
        ↓ issue created
Issue Triage Agent  (label + classify severity)
        ↓ triaged issue
Security Scanner Agent  (validate the finding)
        ↓ validated + confirmed
Autopilot Fix Agent  (fork → clone → fix → push → open PR)
        ↓ PR opened
Notify Agent  (Slack — finding captured, PR opened)
```

Each agent is a standalone Conduct agent with its own:
- Run trace (turns, cost, duration)
- Input/output state
- Credentials (GitHub, Slack)
- Guard policy enforcement

The chain is triggered by events passing between agents — not a single monolithic playbook. State flows forward automatically.

### Why this matters

Security Loop is the first real proof point of **agent orchestration** on Conduct — a platform where chains of specialized agents collaborate on a task end to end.

Once this pattern is established:

- **Swappable agents** — replace the fix agent with a different strategy (patch-only, full refactor, dependency bump) without touching the rest of the chain
- **Branching chains** — critical findings take one path (auto-run), medium findings take another (draft + human approval)
- **Reusable pattern** — the same chain architecture applies to any multi-step workflow beyond security: release pipelines, incident response, dependency management
- **Per-agent observability** — every agent in the chain has its own cost, turns, and trace. You can see exactly where time and money is spent

### The moat

Not any single playbook. Conduct as the platform where agents chain into autonomous workflows — each agent specialized, each step traced, the whole thing visible in one dashboard.

Security Loop is the first chain. It proves the pattern. Everything after it gets easier.

---

---

## 19. Observations Dashboard

Every step of every agent in the chain is captured, costed, and auditable in one dashboard. This is both the operational view for engineers and the compliance evidence for security teams.

### Per-run view (single Security Loop chain run)

```
Step                    Agent                 Duration   Cost     Detail
─────────────────────────────────────────────────────────────────────────
Finding detected        security-loop-cli     0m 02s     —        claude-bughunter · HIGH · path-traversal
Issue created           github (tool)         0m 03s     —        issue #47 in owner/repo
Triage fired            issue-triage          0m 28s     $0.04    severity: high · labels: security, bug
Scanner validated       security-scanner      1m 12s     $0.18    confirmed: path-traversal in scripts/cbh.py
Fix applied             autopilot-fix         1m 52s     $0.38    2 files changed · branch pushed
PR opened               github (tool)         0m 04s     —        PR #15 → main
Slack notified          slack (output)        0m 02s     —        #security notified
─────────────────────────────────────────────────────────────────────────
Total                                         3m 43s     $0.61    7 steps · approved by: sudhi@
```

### Workspace-level observations (across all findings)

| Metric | What it shows |
|---|---|
| Findings captured | Total this week, by tool (claude-bughunter, codex, cursor) |
| Findings by severity | Critical / high / medium / low breakdown |
| Findings by repo | Which repos surface the most issues |
| Pipeline completion rate | % findings that reached PR stage vs dropped |
| Mean time to PR (MTTP) | Average time from detection to PR opened |
| Mean time to merge (MTTM) | Average time from PR open to merged (human step) |
| Cost per finding | Average $ spent per finding resolved |
| Slowest step | Which agent in the chain takes the most time |
| Most expensive step | Which agent costs the most per run |
| Tools connected | Which AI tools are actively emitting findings |

### Compliance export

A CISO or security lead can export a finding report showing:

```
Finding ID    Tool             Severity  Repo                    Detected        Reviewed by    PR          Merged
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
SL-001        claude-bughunter HIGH      elementalsouls/cbh      2026-06-05      sudhi@         PR #15      2026-06-05
SL-002        codex            MEDIUM    owner/repo              2026-06-06      —              draft       —
```

Every row is a tamper-evident run trace with a unique run ID, timestamps at every step, approver identity, PR link, and cost. Sufficient for SOC 2, internal audits, and board-level security reviews.

### The claim

> "Every vulnerability your AI coding tools find — detected, triaged, fixed, and shipped as a PR — with a full audit trail in one dashboard. Across Claude Code, Codex, and Cursor."

No other tool closes this loop. They all stop at surfacing the finding. Conduct is what happens next.

---

## 18. Agent Chaining — Future Platform Primitive

> Not building now. Captured for roadmap.

### The idea

Today every agent is `simple` — one playbook, one run, one trace. A `chain` agent type would let you wire independent agents together so each one's output becomes the next one's input. Security Loop would be the first chain.

### New agent type: `chain`

```yaml
type: chain
agents:
  - security_findings_agent
  - issue_triage_agent
  - security_scanner_agent
  - autopilot_fix_agent
  - notify_agent
```

Each node is a fully deployed agent with its own playbook, credentials, turn budget, and Guard policy. The chain runner spawns child runs sequentially and passes state forward.

### What changes across the platform

**Canvas** — chain agents open a different view: agent nodes connected by arrows instead of blocks inside a single flow.

```
[Security Findings] → [Issue Triage] → [Security Scanner] → [Autopilot Fix] → [Notify]
     agent node            agent node        agent node          agent node      agent node
```

**Agent card** — new type badge alongside existing ones:

```
security_loop    CHAIN    Security Engineering
autopilot        SIMPLE   Backend
```

**Run feed** — chain run shows a parent row that expands to reveal each child agent run inline, each with its own turns, cost, duration, and trace.

```
▶ security_loop  CHAIN  3m 42s  $0.61  5 agents
  ├─ ✓ security_findings_agent   0m 04s  $0.00
  ├─ ✓ issue_triage_agent        0m 28s  $0.04
  ├─ ✓ security_scanner_agent    1m 12s  $0.18
  ├─ ✓ autopilot_fix_agent       1m 52s  $0.38
  └─ ✓ notify_agent              0m 06s  $0.01
```

**API** — chain runner spawns child runs, passes `output` of each run as `initial_state` of the next.

### Minimum viable start (when ready to build)

1. Type badge (`SIMPLE` / `CHAIN`) on agent cards and run feed — display only, no new canvas
2. Chain run feed — parent row + nested child runs
3. Chain YAML schema + chain runner in the executor
4. Canvas chain view — agent nodes instead of blocks (last, most complex)

### Why this is the moat

Simple agents are replicable. A platform where specialized agents chain into autonomous multi-step workflows — each step traced, each agent swappable, the whole thing observable in one dashboard — is not.

Security Loop proves the pattern. The chain primitive makes it reusable for every workflow on Conduct.

---

---

## 20. BugHunter Integration — Active Hunt Mode

> Added v0.3. Covers the integration of Claude-BugHunter as an active vulnerability scanner feeding the Security Loop pipeline.

### Two modes: passive capture vs active hunt

The existing spec covers **passive capture** — AI tools surface findings as a side effect of normal coding work, Guard intercepts them, Conduct closes the loop.

BugHunter adds **active hunt mode** — a targeted scan of a specific repo or URL using structured hunting methodology. The output feeds the same Security Loop pipeline.

```
PASSIVE (existing)                     ACTIVE (new — BugHunter)
─────────────────────────────          ──────────────────────────────────
Developer works with Claude Code  →    Security engineer points BugHunter
Guard intercepts incidental finding    at a target repo or URL
        ↓                                      ↓
Finding classifier                     8 hunt skills run sequentially
        ↓                                      ↓
POST /security-findings                Structured findings emitted per skill
        ↓                                      ↓
Same pipeline: triage → fix → PR       Same pipeline: triage → fix → PR
```

### The 8 hunt skills and their Security Loop mapping

Each BugHunter skill maps to a finding `type` in the Security Loop schema. When a skill fires, the emitter populates the `type` field so the triage agent knows which remediation playbook to invoke.

| BugHunter skill | Finding type | Severity default | Remediation playbook |
|---|---|---|---|
| `hunt-llm-injection` | `llm-injection` | high | security-scanner → autopilot-fix |
| `hunt-jwt-confusion` | `auth-bypass` | critical | security-scanner → autopilot-fix |
| `hunt-graphql` | `idor` / `injection` | high | security-scanner → autopilot-fix |
| `hunt-oauth-oidc` | `auth-bypass` | critical | security-scanner → autopilot-fix |
| `hunt-ssrf-cloud` | `ssrf` | critical | security-scanner → autopilot-fix |
| `hunt-websocket` | `auth-bypass` / `injection` | high | security-scanner → autopilot-fix |
| `hunt-supply-chain` | `supply-chain` | critical | security-scanner → autopilot-fix |
| `hunt-race-conditions` | `race-condition` | high | security-scanner → autopilot-fix |

### `conduct hunt` CLI command

New CLI command that kicks off a targeted BugHunter scan against a repo and pipes findings into the Security Loop:

```bash
# Scan a GitHub repo — hunt all 8 skill classes
conduct hunt --repo owner/repo --skills all

# Scan a target URL (API surface, web app)
conduct hunt --url https://target.com --skills llm-injection,graphql,oauth-oidc

# Run a specific skill only
conduct hunt --repo owner/repo --skill hunt-jwt-confusion

# Dry run — show what would be emitted, no pipeline trigger
conduct hunt --repo owner/repo --skills all --dry-run
```

**Flow:**
```
conduct hunt --repo owner/repo --skills all
        ↓
For each skill in the run set:
  1. Load SKILL.md from Claude-BugHunter (via installed plugin or local cache)
  2. Invoke Claude (Sonnet) with the skill as context + target repo/URL
  3. Claude runs the methodology, produces structured findings
  4. Emitter maps findings to Security Loop schema
  5. POST /security-findings for each confirmed finding
        ↓
/security console page shows findings in real-time as skills complete
```

### Hunt playbook YAML

A new Conduct playbook that orchestrates the hunt across all 8 skills:

```yaml
name: bughunter-active-scan
description: Run Claude-BugHunter skills against a target and feed findings into the Security Loop pipeline.

input:
  target_repo:
    type: string
    description: GitHub repo to scan (owner/repo format)
  target_url:
    type: string
    description: Optional target URL for web-facing surface scan
  skills:
    type: array
    items:
      enum:
        - hunt-llm-injection
        - hunt-jwt-confusion
        - hunt-graphql
        - hunt-oauth-oidc
        - hunt-ssrf-cloud
        - hunt-websocket
        - hunt-supply-chain
        - hunt-race-conditions
    default:
      - hunt-llm-injection
      - hunt-jwt-confusion
      - hunt-graphql
      - hunt-oauth-oidc
      - hunt-ssrf-cloud
      - hunt-websocket
      - hunt-supply-chain
      - hunt-race-conditions
  severity_threshold:
    type: string
    enum: [critical, high, medium, low]
    default: medium
    description: Only emit findings at or above this severity

blocks:
  - id: load_skills
    type: tool
    action: bughunter/load_skills
    input:
      skills: "{{ input.skills }}"

  - id: run_hunt
    type: brain
    model: claude-sonnet-4-6
    for_each: "{{ load_skills.output.skills }}"
    system: |
      You are a security researcher running the {{ item.name }} hunt skill.
      Target: {{ input.target_repo }}{% if input.target_url %} ({{ input.target_url }}){% endif %}
      
      Follow the methodology in the skill exactly. For each finding you confirm:
      - Assign severity: critical | high | medium | low
      - Classify type using the finding type map
      - Provide: file/endpoint, description, suggested fix, evidence
      
      Output ONLY confirmed findings with sufficient evidence. Do not speculate.
      Output format: JSON array of finding objects, or empty array if no findings.
    prompt: |
      Run the {{ item.name }} hunt against the target.
      
      Skill methodology:
      {{ item.content }}
      
      Return findings as JSON:
      [{"severity": "...", "type": "...", "file": "...", "description": "...", "suggested_fix": "...", "evidence": "..."}]

  - id: emit_findings
    type: tool
    action: security_loop/emit_findings
    input:
      findings: "{{ run_hunt.output }}"
      tool: "claude-bughunter"
      repo_full_name: "{{ input.target_repo }}"
      severity_threshold: "{{ input.severity_threshold }}"

  - id: notify_summary
    type: output
    channels:
      - slack
    template: |
      🔍 BugHunter scan complete — {{ input.target_repo }}
      Skills run: {{ input.skills | length }}
      Findings emitted: {{ emit_findings.output.count }}
      Critical: {{ emit_findings.output.by_severity.critical | default(0) }}
      High: {{ emit_findings.output.by_severity.high | default(0) }}
      → View in Conduct: {{ emit_findings.output.console_url }}
```

### Guard policies derived from hunt findings

As the Security Loop runs hunts against real targets, high-confidence patterns get promoted to Guard policies. This closes the learning loop — hunt findings become standing protection for Conduct's own agent fleet.

| Hunt finding type | Resulting Guard policy |
|---|---|
| `llm-injection` confirmed in target | Block: agent tool calls where output contains known injection signatures |
| `ssrf-cloud` confirmed | Alert: agent making HTTP requests to `169.254.169.254` or `metadata.google.internal` |
| `jwt-confusion` confirmed | Block: agents issuing or consuming JWTs without algorithm allowlist |
| `supply-chain` (Actions injection) | Alert: agent modifying `.github/workflows/` files with unvalidated input |
| `race-conditions` (financial) | Alert: agent making concurrent writes to the same financial resource |

Guard policies are stored in the workspace policy set and enforced by ConductGuard on all subsequent agent runs. The policy is linked back to the Security Loop run that generated it — full audit trail from hunt finding → Guard policy → enforcement event.

### Build additions (v0.3)

These items extend the build list in section 15:

| What | Layer | Effort |
|---|---|---|
| `conduct hunt` CLI command | CLI — Python | Medium |
| `bughunter/load_skills` action | API — playbook actions | Small |
| `security_loop/emit_findings` action | API — playbook actions | Small |
| `bughunter-active-scan` playbook YAML | Playbook | Small |
| Hunt-to-Guard-policy promotion logic | API — business logic | Medium |
| `/security` page — active hunts tab | Frontend | Small |
| Guard policy creation from finding | Guard CLI + API | Medium |

### Critical path addition

```
conduct hunt CLI command
        ↓
bughunter/load_skills action (fetches skill SKILL.md content)
        ↓
brain block runs per skill (Claude Sonnet with skill as context)
        ↓
security_loop/emit_findings action → POST /security-findings (already on critical path)
        ↓
Guard policy promotion (after N confirmed findings of same type)
```

The hunt playbook is unblocked as soon as `POST /security-findings` exists. It can be built and smoke-tested in parallel with the `/security` console page.

---

*Conduct AI · SECURITY_LOOP_SPEC.md · v0.3*
