# Conduct Security Loop
**v0.2 · June 5, 2026**

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

*Conduct AI · SECURITY_LOOP_SPEC.md · v0.2*
