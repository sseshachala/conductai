# ConductAI: Agent Inventory Scan
## Product Spec + Build Plan
**Version 1.0 | June 2026**

---

## 1. The Problem in One Sentence

Enterprises cannot govern AI agents they don't know exist.

---

## 2. What We're Building

A free CLI command — `conduct scan` — that discovers every AI agent and tool
running in a developer's environment, scores each one for governance risk, and
outputs a posture report. Zero configuration required. Runs in under 60 seconds.

The scan feeds a paid **Agent Inventory Dashboard** in conductai.ai — a live,
org-wide view of what agents are running, what they can touch, and what's
drifting from policy.

**Free tier:** `conduct scan` — local scan, terminal/HTML output, shareable JSON  
**Paid tier:** Dashboard, org-wide aggregation, drift alerts, compliance exports

---

## 3. What It Discovers

### Layer 1 — Developer Tool Agents (already covered by claude_audit.py)
| Surface | What we detect |
|---|---|
| Claude Code | MCP servers, hooks, subagents, skills, CLAUDE.md |
| Cursor | `.cursor/mcp.json`, rules files, tool permissions |
| Windsurf | Cascade config, MCP wiring |
| VS Code Copilot | extensions.json, GitHub Copilot settings |
| Custom agents | Processes calling LLM APIs (OpenAI, Anthropic, Gemini) |

### Layer 2 — SaaS Agent Surfaces (new)
| Surface | What we detect |
|---|---|
| Slack | Installed bots/apps with write permissions |
| Microsoft Teams | Registered bots, Power Automate flows with AI steps |
| Notion AI | Workspace AI features, automation rules |
| Atlassian | Rovo agents, Forge apps |
| Atomicwork / ServiceNow | ITSM agents (via API key, if provided) |

### Layer 3 — Infrastructure (new)
| Surface | What we detect |
|---|---|
| .env files | LLM API keys (OpenAI, Anthropic, Cohere, Gemini) |
| Docker/k8s | Containers running known LLM inference ports |
| CI/CD | GitHub Actions / GitLab CI steps calling LLM APIs |
| AWS/GCP/Azure | Lambda/Cloud Functions with LLM env vars |

---

## 4. Risk Scoring Model

Each discovered agent gets a **Posture Score (0–100)**, lower = riskier.

```
Score = 100
  - 30  if no audit logging configured
  - 20  if has file system write access
  - 20  if has outbound network access + no allowlist
  - 15  if no human approval gate on actions
  - 10  if credentials stored in plaintext
  - 10  if no policy version pinned
  + 10  if ConductGuard active on this agent
  + 5   if last reviewed < 30 days ago
```

**Posture bands:**
- 🔴 CRITICAL: 0–39
- 🟠 AT RISK: 40–59
- 🟡 PARTIAL: 60–79
- 🟢 GOVERNED: 80–100

---

## 5. Output Formats

### Terminal (default)
```
conduct scan

ConductAI Agent Inventory Scan v0.1.0
Scanning: /Users/sudhi/projects/conductai + ~/.claude
──────────────────────────────────────────────────
AGENT                    TYPE          POSTURE   ISSUES
claude-code-main         Claude Code   47 ⚠️     3 HIGH, 1 MED
cursor-assistant         Cursor        61 🟡     1 HIGH
atomicwork-atom          ITSM Agent    22 🔴     5 HIGH
gh-actions-deployer      CI Agent      38 🔴     2 HIGH
slack-zapier-bot         SaaS Bot      55 🟠     2 MED
──────────────────────────────────────────────────
5 agents found. 2 CRITICAL. 0 governed.
Run: conduct scan --html > report.html  for full report
Run: conduct connect  to sync to conductai.ai dashboard
```

### HTML Report
Same as claude_audit.py HTML output — dark themed, severity filters,
per-agent expandable findings, remediation checklist per finding.

### JSON (for CI/SIEM ingestion)
```json
{
  "scan_id": "scn_abc123",
  "timestamp": "2026-06-16T10:00:00Z",
  "agents": [
    {
      "id": "claude-code-main",
      "type": "claude_code",
      "posture_score": 47,
      "posture_band": "AT_RISK",
      "findings": [...]
    }
  ],
  "summary": {
    "total": 5,
    "critical": 2,
    "governed": 0
  }
}
```

---

## 6. Build Plan

### What Already Exists (Don't Rebuild)
- `claude_audit.py` — 7-surface Claude Code auditor, HTML output, `--comply` flag
- `conduct-cli` — distribution mechanism, v0.4.40, PyPI via Trusted Publishing
- `ConductGuard` — 34 active policy rules, MCP-based enforcement
- Risk scoring logic — partially in claude_audit.py severity model

### Phase 1: `conduct scan` CLI Command (ship first)
**Goal:** Free, zero-config local scan. Shareable JSON + HTML output.
**Scope:** Claude Code + Cursor + Windsurf + `.env` key detection + posture score + HTML/JSON output.

| Task | Effort |
|---|---|
| Port claude_audit.py surfaces into conduct-cli as `scan` subcommand | 3d |
| Add Cursor detection (`.cursor/mcp.json`, rules) | 1d |
| Add Windsurf detection | 1d |
| Add `.env` crawler for LLM API key detection | 1d |
| Implement posture scoring model | 2d |
| HTML report template (from claude_audit.py base) | 1d |
| JSON output + scan_id generation | 1d |
| Tests + smoketests | 1d |
| **Total** | **~11d** |

> Skipped for Phase 1: Docker/k8s scanner, CI/CD YAML parser, SaaS integrations (Atomicwork/ServiceNow). Add when Phase 1 has traction.

### Phase 2: Dashboard Sync (validate first)
**Goal:** `conduct connect` pushes scan results to conductai.ai. Org-wide view.
**Trigger:** 200+ scans in the wild, users asking for org aggregation.

| Task | Effort |
|---|---|
| `conduct connect` — auth + org enrollment | 3d |
| Scan upload API endpoint | 3d |
| Agent Inventory data model (Postgres) | 2d |
| Dashboard UI — agent list, posture scores, filter | 5d |
| Org aggregation — merge scans from multiple devs | 3d |
| **Total** | **~16d** |

### Phase 3: Live Drift Detection (after Phase 2 proven)
**Goal:** Continuous monitoring. Alert when posture changes.

| Task | Effort |
|---|---|
| Scheduled scan daemon (`conduct scan --watch`) | 3d |
| Drift detection — diff two scan snapshots | 3d |
| Alert engine — Slack/email on posture degradation | 3d |
| Compliance export — PDF for SOC2/ISO42001 evidence | 4d |
| **Total** | **~13d** |

---

## 7. Go-To-Market Motion

### Launch: Free `conduct scan`
- Ship as `conduct scan` in conduct-cli v0.5.0
- Blog post: "We scanned 50 dev environments. Here's what we found."
- LinkedIn + HN post with terminal screenshot showing real findings
- CTA: `pip install conduct-cli && conduct scan`

### Conversion: Dashboard
- Terminal output ends with: `→ See your full inventory at conductai.ai/scan/abc123`
- Link opens read-only web view of the scan
- "Connect your org" = paid conversion

### Enterprise Motion
- CISO gets the HTML report from a developer
- Report shows ungoverned agents with specific finding IDs
- ConductAI dashboard = remediation platform
- ConductGuard = enforcement layer

---

## 8. Competitive Positioning

| Capability | ConductAI | Straiker | Atomicwork |
|---|---|---|---|
| Developer tool layer (Claude Code, Cursor) | ✅ Native | ❌ | ❌ |
| MCP-level enforcement | ✅ ConductGuard | ❌ | ❌ |
| Free scan, zero config | ✅ | ❌ Enterprise only | ❌ |
| Works without IT involvement | ✅ | ❌ | ❌ |
| ITSM agent visibility | 🔜 Phase 3 | ✅ | ✅ Own agents only |

**Moat:** Lives inside the developer's tool, not above it. Straiker sells to CISOs top-down. Conduct lands with developers bottom-up, surfaces findings to the CISO.

---

## 9. Success Metrics (90 days post-launch)

| Metric | Target |
|---|---|
| `conduct scan` installs | 500+ |
| Scans run | 2,000+ |
| Dashboard signups (free) | 200+ |
| Paid conversions | 10+ |
| Design partner enterprises | 3 |

---

## 10. Immediate Next Step

Run `conduct scan` on ConductAI and Narratr repos first.
Publish findings (anonymized) as launch content.
Dogfooding is the most credible GTM asset.
