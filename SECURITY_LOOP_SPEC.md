# Conduct Security Loop
**v0.1 · June 5, 2026**

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

### 6a. Finding emitter per tool

Thin event emitter that fires when an AI tool surfaces a security finding and POSTs to Conduct's webhook endpoint.

| Tool | Mechanism | Effort |
|---|---|---|
| Claude Code | `PostToolUse` hook in `.claude/settings.json` | Low — Guard hook already exists |
| Codex CLI | `after_tool` hook in `codex.toml` | Low — same pattern |
| Cursor | Rules file + background agent | Medium |
| GitHub Copilot | PR comment webhook → Conduct | Low — webhook already supported |

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

**Week 1–2**
- `security_finding` trigger shape in input_contract.py
- Finding emitter for Claude Code (PostToolUse hook in ConductGuard)
- Security Loop playbook YAML

**Week 3–4**
- Finding emitter for Codex CLI
- `create_issue` action in GitHub integration
- End-to-end smoke test: Claude Code finding → PR in one run

**Week 5–6**
- Dashboard Security Loop feed (findings status view)
- Copilot PR comment → webhook path
- Export / compliance report

**Week 7–8**
- Cursor integration
- MTTF metric in dashboard
- Launch blog post + demo video

---

## 12. Open Questions

1. Should dismissed findings (false positives) be tracked separately in the dashboard?
2. Do we want human approval gates before the fix branch is pushed? (autopilot-approved pattern)
3. Should the finding emitter be part of ConductGuard CLI or a separate lightweight binary?
4. Severity threshold — should low/info findings auto-close without creating an issue?

---

*Conduct AI · SECURITY_LOOP_SPEC.md · v0.1*
