# ConductGuard — Spend Controls

ConductGuard enforces AI spend limits at two levels: workspace (the whole team) and per-developer. Limits are checked on every tool call before it executes.

---

## Budget Types

| Budget type | Scope | Enforced by |
|---|---|---|
| **Workspace hard cap** | All developers in the workspace combined | `hard_limit_usd` on the workspace budget row |
| **Per-developer cap** | Individual developer's monthly spend | `monthly_limit_usd` on a developer-scoped budget row (`clerk_user_id` set) |
| **Alert threshold** | Notify Slack when spend reaches N% of limit | `alert_threshold_pct` (default 80%) |

---

## How Enforcement Works

On every PreToolUse hook call, the CLI sends a request to:

```
POST /guard/spend/budget-check
{
  "workspace_id": "...",
  "clerk_user_id": "user_...",
  "monthly_cost_usd": 42.15
}
```

The API checks:

1. **Workspace hard cap** — if current month's total spend across all developers ≥ `hard_limit_usd`, returns `hard_blocked: true`
2. **Per-developer cap** — if this developer's spend ≥ their `monthly_limit_usd`, returns `hard_blocked: true`
3. **Alert threshold** — if spend crossed a new 5% increment above `alert_threshold_pct`, sends a Slack alert (deduped — fires once per 5% band, not on every call)

When `hard_blocked: true`, the hook exits with code 2 and shows the message inline in Claude Code:

```
# Workspace block:
Your team's monthly AI budget of $50.00 has been reached.
New tool calls are paused until the limit is raised.
Contact your security team.

# Per-developer block:
You've reached your monthly AI spend limit of $25.00.
New tool calls are paused. Contact your manager to have your limit raised.
```

---

## Setting Budgets (Admin Only)

Go to **Guard → Spend** in the ConductGuard dashboard.

### Workspace budget

| Field | Description |
|---|---|
| Monthly limit | Alert fires when spend crosses `alert_threshold_pct` of this |
| Hard cap | All tool calls blocked when this is reached |
| Alert threshold | % of monthly limit that triggers a Slack notification (default 80%) |

### Per-developer budget

Set a `Default per developer` limit to apply the same cap to all developers. Override individual developers by selecting them from the member list.

Budget inputs accept values as low as $0.01 — useful for testing enforcement on small amounts.

---

## Slack Alerts

When spend crosses an alert threshold, a Slack message is posted to the configured alert channel:

```
🟡 ConductGuard Spend Alert
Team spend has reached 85% of the monthly budget ($50.00).
Current spend: $42.75
Remaining: $7.25
```

Alerts are deduped per 5% increment — if the threshold is 80%, alerts fire at 80%, 85%, 90%, 95%, and 100%. Not on every individual tool call.

Configure the alert channel at **Guard → Settings → Alert channel**.

---

## Cost Tracking

Spend is tracked per session and per audit event. The dashboard shows:

- **Today's cost** — Claude vs Codex breakdown sub-line
- **Cost trend chart** — daily / weekly / monthly stacked bar chart (Claude, Codex, other)
- **Per-developer breakdown** — who is spending what this month

Cost data comes from the `total_cost_usd` field on `guard_sessions` and `cost_usd_after` on `guard_audit_events`, populated by the PostToolUse hook from Claude Code's token usage data.

---

## Database Schema

```sql
-- guard_spend_budgets
id                      UUID  primary key
workspace_id            UUID  FK → workspaces
clerk_user_id           TEXT  NULL = workspace-level; set = per-developer
monthly_limit_usd       FLOAT not null
hard_limit_usd          FLOAT nullable
alert_threshold_pct     INT   default 80
default_per_developer_usd FLOAT nullable
last_alert_pct_bucket   INT   nullable  -- dedup: last 5%-band that fired an alert
```

---

## Reconciliation with Actual API Bills

ConductGuard spend tracking is based on token counts reported by Claude Code's hook system — it is not reconciled against Anthropic or OpenAI invoices. Use it for relative tracking and enforcement. For billing reconciliation, compare against your Anthropic Console usage report.

> Tracked in: [GitHub Issue — billing reconciliation](https://github.com/sseshachala/conductai/issues)
