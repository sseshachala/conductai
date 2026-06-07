# Conduct Security Loop
**v0.4 · June 7, 2026**

---

## TL;DR

AI coding tools surface security findings constantly. None of them close the loop.
Conduct is the response layer: capture findings from any AI tool → surface on `/security` →
route through triage → fix → PR pipeline, with a full audit trail per finding.

**The claim:** Connect your AI tools to Conduct once. Every security issue they find
automatically surfaces on your team's security feed. Fix pipeline runs on demand (manual now,
autopilot in Phase 2).

---

## 1. The Problem

Engineering teams run 2–4 AI coding tools simultaneously. Each surfaces findings differently:

- Claude Code prints to terminal, fires hooks
- Codex CLI outputs inline, has a hook system
- Cursor shows inline suggestions with no external routing
- GitHub Copilot posts PR comments

**Nothing connects these findings to action.** A finding surfaced at 2pm on Thursday:
- May or may not become a GitHub issue
- May or may not get triaged for severity
- May or may not get fixed before the next release
- Definitely has no audit trail linking detection → remediation

For security teams: compliance gap. For engineering managers: invisible risk.

---

## 2. Three Entry Points, One Feed

All findings flow into `/security-findings` API → `/security` console page.

```
┌─────────────────────────────────────────────────────────────────┐
│                     THREE ENTRY POINTS                          │
├────────────────────┬──────────────────┬─────────────────────────┤
│  PASSIVE           │  ACTIVE SCAN     │  MANUAL                 │
│  Guard PostToolUse │  BugHunter       │  conduct emit finding   │
│  hook              │  Active Scan     │  --from-stdin           │
│  (always on when   │  playbook        │  (power user / testing) │
│  flag enabled)     │  (on demand)     │                         │
└────────────────────┴──────────────────┴─────────────────────────┘
                              ↓
                   POST /security-findings
                              ↓
                    /security console page
                              ↓
                   User clicks "Run fix pipeline"
                              ↓
              security-loop.yaml playbook runs:
              GH issue → security-autopilot-fix → PR → Slack
```

---

## 3. Entry Points in Detail

### 3a. Passive — Guard PostToolUse Hook

- Already hooked inside Claude Code and Codex CLI via `conduct login`
- When **Security Emit** flag is ON in Guard settings, classifier runs on every tool call output
- If finding detected → POST to `/security-findings` automatically (zero developer action)
- **Fast-path classifier** (regex, zero latency, always runs):
  - Hardcoded secrets: `sk-`, `ghp_`, `AKIA`, `Bearer`, `password =`, `api_key =`
  - Path traversal: `../../../`, `file://`
  - Code injection: `eval(`, `exec(`, `__import__`
  - Crypto bypass: `ssl.CERT_NONE`, `verify=False`
- **Keyword classifier** (OWASP terms in Claude Code output):
  - SQL injection, XSS, IDOR, SSRF, command injection, auth bypass

### 3b. Active Scan — BugHunter Active Scan Playbook

- User installs `bughunter-active-scan` playbook from marketplace
- User runs: `conduct run "BugHunter Active Scan" --input target_repo=owner/repo`
- 8 targeted hunt skills run against the repo:

| Skill | Covers |
|---|---|
| `hunt-llm-injection` | Prompt injection, jailbreaks in LLM-facing endpoints |
| `hunt-jwt-confusion` | Algorithm confusion, none alg, weak secrets |
| `hunt-graphql` | Introspection, batching, injection via queries |
| `hunt-oauth-oidc` | PKCE bypass, implicit flow, token leakage |
| `hunt-ssrf-cloud` | SSRF → metadata endpoints, cloud credential theft |
| `hunt-websocket` | Origin bypass, cross-site hijacking |
| `hunt-supply-chain` | Dependency confusion, typosquatting, malicious packages |
| `hunt-race-conditions` | TOCTOU, concurrent request races |

- Each confirmed finding → POST to `/security-findings` → surfaces on `/security` page
- **Gap (not yet wired):** `emit_to_security_loop` block in the playbook doesn't call `POST /security-findings` yet

### 3c. Manual — `conduct emit finding --from-stdin`

- Power user / testing tool
- Pipes raw tool output through the fast-path classifier
- If finding detected → POST to `/security-findings`
- Edge case — not the normal user flow. Could move to `conduct debug emit finding`

---

## 4. Guard Settings — 2 New Flags

Located in Guard settings UI (admin only). Stored in `guard_config` table.

| Flag | DB column | Default | Description |
|---|---|---|---|
| **Security Emit** | `security_emit_enabled` | false | Classifier runs on every Claude Code tool call. Findings surface on /security page automatically |
| **Security Slack Alerts** | `security_slack_alerts_enabled` | false | When a finding is detected, POST to a dedicated Slack channel with: developer name, session ID, severity, file, description |

**Slack alert config** (shown when Security Slack Alerts is ON):
- Channel name field: e.g. `#security-alerts`
- Message format: `[HIGH] secret-leak in config.py:12 — Sudhi's session (abc123) · claude-code`

---

## 5. Finding Schema

```json
{
  "tool": "claude-code | codex | cursor | copilot | bughunter | manual",
  "severity": "critical | high | medium | low | info",
  "type": "injection | path-traversal | secret-leak | auth-bypass | crypto | other",
  "file": "config.py",
  "line": 12,
  "description": "Hardcoded AWS key found in config file",
  "suggested_fix": "Move to environment variable, rotate the key",
  "repo_full_name": "owner/repo",
  "commit_sha": "abc1234",
  "source_run_id": "optional — if surfaced inside a BugHunter run"
}
```

---

## 6. Fix Pipeline — Manual Trigger (Phase 1)

User sees finding on `/security` page → clicks **"Run fix pipeline"** → `security-loop.yaml` playbook runs.

```
security-loop.yaml
        ↓
recall_context (prior findings on this repo)
        ↓
create_github_issue (severity label, security label, suggested fix in body)
        ↓
security-autopilot-fix playbook (fork → fix branch → apply patch → PR)
        ↓
notify_slack (#security-alerts or configured channel)
        ↓
record_outcome (write result back to memory, update finding status → "triaging")
```

Phase 2: **Auto-Fix Pipeline** flag (off by default) — skips the manual click, runs automatically on every new finding above severity threshold.

---

## 7. /security Console Page

### KPI Strip (top)
| Card | Value | Color logic |
|---|---|---|
| Open | count status=open | Red if >0, green if 0 |
| Critical / High | count severity ∈ {critical, high} | Red if >0, green if 0 |
| Fixed this month | count status=fixed last 30d | Always green |
| MTTR | avg hours created→fixed | Neutral |

### Findings Table
Severity pill | Type | File:line | Description | Tool | Repo | Age | Status | [Run fix] button

### Severity Pill Colors
- critical → red `#fee2e2 / #dc2626`
- high → orange `#fff7ed / #ea580c`
- medium → yellow `#fefce8 / #ca8a04`
- low → blue `#eff6ff / #2563eb`
- info → stone `#f5f5f4 / #78716c`

---

## 8. API Surface

| Method | Endpoint | Auth | Description |
|---|---|---|---|
| POST | `/security-findings` | authenticated user | Ingest a finding |
| GET | `/security-findings` | guard.activity.view_all | List findings (filterable) |
| GET | `/security-findings/summary` | guard.activity.view_all | KPI stats + MTTR |
| GET | `/security-findings/{id}` | guard.activity.view_all | Single finding |
| PATCH | `/security-findings/{id}` | guard.policies.edit | Update status / GH issue URL |

---

## 9. Build Status

### Done ✓
| What | Where |
|---|---|
| `conduct emit finding` CLI command + fast-path classifier | `packages/conduct-cli` v0.4.50 |
| `POST /security-findings` API + all endpoints | `apps/api/app/routers/security.py` |
| `security_findings` DB table + migration 0061 | `apps/api/alembic/versions/0061` |
| `security_finding` trigger shape in input_contract | `apps/api/app/runtime/input_contract.py` |
| `/security` console page | `apps/web/src/app/security/page.tsx` |
| Security nav link | `apps/web/src/components/AppShell.tsx` |
| `bughunter-active-scan.yaml` playbook (8 hunt skills) | `apps/api/playbooks/` |

### Gaps — Build Next
| What | Effort | Blocks |
|---|---|---|
| 2 Guard flags in `guard_config` DB + migration | Small | Everything passive |
| Guard settings UI — Security Emit + Slack Alerts toggles + channel field | Small | Flag management |
| Guard PostToolUse hook extension (call classifier → POST /security-findings) | Medium | Passive capture |
| Slack alert on new finding (developer name + session) | Small | Slack visibility |
| `security-loop.yaml` playbook | Medium | Fix pipeline |
| Wire `emit_to_security_loop` block in `bughunter-active-scan.yaml` | Small | Active scan → /security |
| "Run fix pipeline" button on `/security` page finding row | Small | Manual fix trigger |
| `github/create_issue` action in `github.py` | Small | Fix pipeline |

### Phase 2 (deferred)
| What | Notes |
|---|---|
| Auto-Fix Pipeline flag (3rd Guard flag) | Auto-run fix pipeline on every finding — risky, needs confidence threshold |
| Classifier slow path (Haiku LLM) | For ambiguous output that regex doesn't catch |
| MTTR metric (full) | Needs GH issue close webhook to close the loop |
| Cursor integration | No hook system — needs MCP bridge |
| Copilot integration | PR comment webhook path |

---

## 10. Build Order (Next Session)

```
1. guard_config migration — add security_emit_enabled, security_slack_alerts_enabled, security_slack_channel
2. Guard settings UI — 2 toggles + channel name field
3. Guard PostToolUse hook — call classifier → POST /security-findings when flag ON
4. Slack alert on finding ingest (POST /security-findings → check flag → send Slack)
5. security-loop.yaml playbook
6. Wire bughunter-active-scan emit_to_security_loop block → POST /security-findings
7. "Run fix pipeline" button on /security page → POST /workflows/{security-loop-id}/trigger
8. github/create_issue action
```

---

## 11. The Claim (when fully built)

> "Connect your AI coding tools to Conduct once via `conduct login`.
> Enable Security Emit in Guard settings.
> Every finding your team's AI tools surface — from Claude Code, Codex, or a targeted BugHunter scan —
> lands on your security feed automatically, with developer attribution, severity, and a one-click fix pipeline."

No new tools. No new process. Works inside the tools your team already uses.
