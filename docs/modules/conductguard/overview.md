# ConductGuard — Overview

ConductGuard is AI tool fleet management for engineering teams. Think MDM (Mobile Device Management) for laptops — but for Claude Code, Codex, Cursor, and Gemini CLI.

The security or team lead configures policies, budgets, and governance rules once in the ConductGuard dashboard. Every developer's machine receives them automatically within 60 seconds. Developers work exactly as before — governance just happens.

---

## Core Value Proposition

| Without ConductGuard | With ConductGuard |
|---|---|
| No visibility into AI tool usage | Real-time activity dashboard, per-developer |
| No spend controls | Hard caps + alert thresholds per team and per developer |
| No audit trail | Every tool call logged: who, what, when, decision |
| No policy enforcement | Block / warn / audit rules enforced at the hook layer |
| Ad-hoc security | Security team sets rules; developers can't override them |

---

## How Control Flows

```
SECURITY / TEAM LEAD
(ConductGuard Dashboard)
        │
        │  Push down (auto-synced every 60s):
        │  ├── Policies (block / warn / audit rules)
        │  ├── Spend budgets (workspace hard cap, per-developer limit)
        │  ├── Alert thresholds (Slack notifications at N% of budget)
        │  └── Approved AI tools
        │
        ▼
Every developer's machine (conduct guard sync)
        │
        │  Report up (real-time):
        │  ├── All AI agent tool calls (what tool, what input, decision)
        │  ├── Token usage and cost (Claude vs Codex)
        │  ├── Policy violations and blocks
        │  └── Session summaries
        │
        ▼
SECURITY / TEAM LEAD
(Dashboard: full picture, live)
```

---

## AI Tools Covered

ConductGuard works by registering a **PreToolUse hook** and **PostToolUse hook** into Claude Code's hook system. The hooks intercept every tool call before it executes.

| AI Tool | Coverage |
|---|---|
| Claude Code | Full — PreToolUse + PostToolUse |
| Codex CLI | Full — PreToolUse + PostToolUse |
| Cursor | Via MCP server (`conductguard-mcp`) |
| Gemini CLI | Via MCP server |

---

## Key Concepts

- **Team** — a ConductGuard team maps 1:1 to a Conduct workspace. All developers in the workspace are Guard team members.
- **Policy** — a named rule with a match condition (tool, pattern, path) and an action (block, warn, audit). Stored in `guard_policies`.
- **Budget** — a monthly USD spend limit. Can be set at workspace level (hard cap) and per-developer. Stored in `guard_spend_budgets`.
- **Session** — a single Claude Code or Codex session. A session groups all tool calls from one invocation.
- **Audit event** — a single tool call record: tool name, input summary, decision, tokens, cost.

---

## Related Docs

- [Developer Setup](developer_setup.md)
- [Hook & Tool Coverage](hook_coverage.md)
- [conductguard-mcp](conductguard_mcp.md)
- [Spend Controls](spend_controls.md)
- [Roles & Permissions](roles_permissions.md)
- [Team Onboarding](team_onboarding.md)
- [Test Scenarios Runbook](../guard_scenarios.md)
- [AI Governance Playbooks](ai_governance_playbooks.md)
