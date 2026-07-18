"""Intent shortcuts — bypass LLM inference for deterministic queries.

Pattern match → call executor service function → return formatted JSON.
Eliminates LLM round-trips for all 16 catalog actions that map to existing APIs.
"""
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.modules.glens.executor import Executor

_ACTIVITY_COLUMNS = [
    {"key": "ts",         "label": "Time",     "type": "date"},
    {"key": "decision",   "label": "Decision", "type": "badge"},
    {"key": "rule_id",    "label": "Rule",     "type": "text"},
    {"key": "ai_tool",    "label": "AI Tool",  "type": "text"},
    {"key": "user_email", "label": "User",     "type": "text"},
]


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _decision_summary(rows: list[dict], total_label: str = "events") -> str:
    if not rows:
        return f"No {total_label} found today."
    counts = Counter(r.get("decision", "allowed") for r in rows)
    parts = [f"{v} {k}" for k, v in counts.most_common()]
    return f"{len(rows)} {total_label} today — {', '.join(parts)}."


# Each entry: (regex, intent) — ordered most-specific first to avoid false matches.
_SHORTCUTS: list[tuple[str, str]] = [
    # Correlated activity — most specific, check before generic block patterns
    (r"relate.{0,10}block.{0,10}(user|action|session)|what.{0,15}user.{0,15}(doing|when).{0,15}block|"
     r"block.{0,10}context|correlat.{0,10}(block|event)|session.{0,10}block",
     "correlated_activity"),
    # Workflow blocks — most specific, check before generic block patterns
    (r"workflow.{0,15}block|block.{0,15}workflow|which.{0,15}workflow|automation.{0,10}block|"
     r"relate.{0,10}block|block.{0,10}context",
     "workflow_blocks"),
    # MTD / monthly KPI — before "blocked today" to avoid false match
    (r"block.{0,15}month|month.{0,15}block|how many block|blocks? mtd|blocks? so far|"
     r"kpi|governance overview|governance summary|risk avoided",
     "governance_kpis"),
    # Guard activity / events today
    (r"guard.?activit|today.{0,10}activit|activit.{0,10}today|"
     r"recent.{0,10}event|event.{0,10}today|event.{0,10}recent|"
     r"what happened today|show.*event",
     "governance_activity"),
    # Blocked today
    (r"who.{0,10}block|block.{0,10}today|today.{0,10}block|show.*block",
     "governance_blocked"),
    # Warned today
    (r"who.{0,10}warn|warn.{0,10}today",
     "governance_warned"),
    # Spend / cost
    (r"spend|cost|how much.{0,15}spend|ai.{0,10}cost|token.{0,10}cost|spending",
     "spend_summary"),
    # Budgets
    (r"budget|spend.{0,10}limit|spending limit",
     "budgets"),
    # Savings
    (r"saving|token.{0,10}save|rtk|booster.{0,10}save|how much.{0,10}save",
     "savings_summary"),
    # Discovery — agents
    (r"discover|which.{0,10}agent|agent.{0,10}running|unprotected.{0,10}agent|"
     r"agent.{0,10}not.{0,10}guard|list.{0,10}agent",
     "discovery_agents"),
    # Policies / rules — require explicit list/show intent to avoid catching create/edit/delete
    (r"show.{0,10}(?:polic|rule)|list.{0,10}(?:polic|rule)|which.{0,10}rule|"
     r"active.{0,10}rule|guard.{0,10}polic|what.{0,10}rule|my.{0,10}rule",
     "list_policies"),
    # Compliance packs / frameworks
    (r"compliance|framework|owasp|soc.?2|hipaa|pci|iso.?42001|gdpr|nist|nis.?2|dora|"
     r"installed.{0,10}pack|which.{0,10}pack",
     "compliance_packs"),
    # Governance narrative
    (r"governance.{0,10}narrative|explain.{0,10}governance|governance.{0,10}health|"
     r"how.{0,10}doing.{0,10}governance|posture",
     "governance_narrative"),
    # Team memory — generic browse (no semantic query)
    (r"team.{0,10}memory|team.{0,10}knowledge|what.{0,10}team.{0,10}know|"
     r"show.{0,10}memory|recent.{0,10}memory|memory.{0,10}feed",
     "team_memory_feed"),
    # Session reports — generic browse
    (r"session.{0,10}report|show.{0,10}session|recent.{0,10}session.{0,10}report|"
     r"agent.{0,10}session.{0,10}report",
     "session_reports_feed"),
]


def try_shortcut(message: str, executor: Executor) -> dict | None:
    """Return a formatted payload dict if we can answer without LLM, else None."""
    low = message.lower()
    for pattern, intent in _SHORTCUTS:
        if re.search(pattern, low):
            return _handle(intent, executor)
    return None


def _handle(intent: str, executor: Executor) -> dict | None:
    today = _today()
    try:
        if intent == "governance_kpis":
            kpis = executor._tool_get_governance_kpis()
            n = kpis.get("events_today", 0)
            b = kpis.get("blocked_today", 0)
            bm = kpis.get("blocks_mtd", 0)
            risk = kpis.get("risk_avoided_usd_mtd", 0)
            return {
                "skill": "governance",
                "ready": True,
                "title": "Governance Overview",
                "answer": f"{n} events today, {b} blocked. {bm} blocks this month, ${risk:,.2f} risk avoided.",
                "component": "GovernanceKpiCards",
                "drilldown": {"path": "/guard"},
                "kpis": [
                    {"label": "Events Today",        "value": n},
                    {"label": "Blocked Today",        "value": b},
                    {"label": "Active Developers",    "value": kpis.get("active_developers_today", 0)},
                    {"label": "Blocks (MTD)",         "value": bm},
                    {"label": "Risk Avoided (MTD)",   "value": f"${risk:,.2f}"},
                ],
                "charts": [],
                "tables": [],
            }
        if intent == "governance_activity":
            rows = executor._tool_get_recent_governance_events(since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows),
                "component": "ActivityTable",
                "drilldown": {"path": "/guard/activity"},
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
        if intent == "governance_blocked":
            rows = executor._tool_get_recent_governance_events(decision="blocked", since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows, "blocks"),
                "component": "ActivityTable",
                "drilldown": {"path": "/guard/activity", "filters": {"decision": "blocked"}},
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
        if intent == "governance_warned":
            rows = executor._tool_get_recent_governance_events(decision="warned", since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows, "warnings"),
                "component": "ActivityTable",
                "drilldown": {"path": "/guard/activity", "filters": {"decision": "warned"}},
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
        if intent == "spend_summary":
            data = executor._tool_get_spend_summary()
            total = data.get("total_cost_usd", 0)
            devs = data.get("by_developer", [])
            return {
                "skill": "analytics",
                "ready": False,
                "answer": f"Total AI spend: ${total:,.4f} across {data.get('active_developers', len(devs))} developer(s).",
                "component": "SpendDashboard",
                "drilldown": {"path": "/guard/spend"},
                "columns": [
                    {"key": "email",    "label": "Developer", "type": "text"},
                    {"key": "cost_usd", "label": "Cost (USD)", "type": "currency"},
                ],
                "rows": devs,
            }

        if intent == "budgets":
            rows = executor._tool_get_budgets()
            return {
                "skill": "analytics",
                "ready": False,
                "answer": f"{len(rows)} budget(s) configured.",
                "component": "BudgetsTable",
                "drilldown": {"path": "/guard/spend/budgets"},
                "columns": [
                    {"key": "scope",              "label": "Scope",          "type": "text"},
                    {"key": "email",              "label": "Developer",      "type": "text"},
                    {"key": "monthly_limit_usd",  "label": "Monthly Limit",  "type": "currency"},
                    {"key": "hard_limit_usd",     "label": "Hard Limit",     "type": "currency"},
                    {"key": "alert_threshold_pct","label": "Alert At",       "type": "percent"},
                ],
                "rows": rows,
            }

        if intent == "savings_summary":
            data = executor._tool_get_savings_summary()
            tokens = data.get("total_tokens_saved", 0)
            usd = data.get("total_cost_saved_usd", 0)
            members = data.get("by_member", [])
            return {
                "skill": "analytics",
                "ready": False,
                "answer": f"{tokens:,} tokens saved (${usd:,.4f}) across {len(members)} developer(s).",
                "component": "SavingsKpiCards",
                "drilldown": {"path": "/guard/spend"},
                "columns": [
                    {"key": "email",                "label": "Developer",         "type": "text"},
                    {"key": "rtk_saved_tokens",     "label": "RTK Saved",         "type": "number"},
                    {"key": "booster_saved_tokens", "label": "Booster Saved",     "type": "number"},
                ],
                "rows": members,
            }

        if intent == "discovery_agents":
            data = executor._tool_get_discovery_summary()
            agents = data.get("agents", [])
            covered = data.get("under_guard", 0)
            total = data.get("total", 0)
            return {
                "skill": "discovery",
                "ready": False,
                "answer": f"{covered} of {total} agent(s) under Guard coverage.",
                "component": "AgentsTable",
                "drilldown": {"path": "/guard/discover"},
                "columns": [
                    {"key": "name",        "label": "Agent",    "type": "text"},
                    {"key": "framework",   "label": "Framework","type": "text"},
                    {"key": "risk_level",  "label": "Risk",     "type": "badge"},
                    {"key": "under_guard", "label": "Covered",  "type": "boolean"},
                    {"key": "last_seen_at","label": "Last Seen","type": "date"},
                ],
                "rows": agents,
            }

        if intent == "list_policies":
            rows = executor._tool_list_policies()
            if not isinstance(rows, list):
                rows = []
            return {
                "skill": "rules",
                "ready": False,
                "answer": f"{len(rows)} Guard rule(s) configured.",
                "component": "PoliciesTable",
                "drilldown": {"path": "/guard/policies"},
                "columns": [
                    {"key": "rule_id",     "label": "Rule ID",     "type": "text"},
                    {"key": "description", "label": "Description", "type": "text"},
                    {"key": "decision",    "label": "Action",      "type": "badge"},
                    {"key": "enabled",     "label": "Enabled",     "type": "boolean"},
                ],
                "rows": rows,
            }

        if intent == "compliance_packs":
            data = executor._tool_get_framework_coverage()
            frameworks = data.get("frameworks", [])
            return {
                "skill": "compliance",
                "ready": False,
                "answer": f"{data.get('installed_count', 0)} compliance framework(s) installed.",
                "component": "CompliancePacksTable",
                "drilldown": {"path": "/guard/compliance"},
                "columns": [
                    {"key": "framework",   "label": "Framework",    "type": "text"},
                    {"key": "rules_count", "label": "Rules",        "type": "number"},
                    {"key": "installed_at","label": "Installed",    "type": "date"},
                ],
                "rows": frameworks,
            }

        if intent == "governance_narrative":
            data = executor._tool_get_governance_narrative()
            return {
                "skill": "governance",
                "ready": False,
                "answer": data.get("paragraph", "Narrative unavailable."),
                "component": "GovernanceNarrative",
                "drilldown": {"path": "/guard"},
            }

        if intent == "correlated_activity":
            data = executor._tool_get_correlated_events(decision="blocked", since=today)
            sessions = data.get("sessions", [])
            total = data.get("total", 0)
            rows = []
            for s in sessions:
                for evt in s.get("events", []):
                    rows.append({
                        "ts":          evt.get("ts"),
                        "decision":    evt.get("decision"),
                        "rule_id":     evt.get("rule_id"),
                        "ai_tool":     evt.get("ai_tool"),
                        "user_email":  s.get("user_email"),
                        "session_started": s.get("started_at"),
                    })
            return {
                "skill": "governance",
                "ready": False,
                "answer": f"{total} block(s) across {len(sessions)} session(s) today.",
                "component": "ActivityTable",
                "drilldown": {"path": "/guard/activity", "filters": {"decision": "blocked"}},
                "columns": [
                    {"key": "ts",              "label": "Time",            "type": "date"},
                    {"key": "rule_id",         "label": "Rule",            "type": "text"},
                    {"key": "ai_tool",         "label": "AI Tool",         "type": "text"},
                    {"key": "user_email",      "label": "User",            "type": "text"},
                    {"key": "session_started", "label": "Session Started", "type": "date"},
                ],
                "rows": rows,
            }

        if intent == "workflow_blocks":
            rows = executor._tool_get_recent_governance_events(
                since=today, limit=50,
                decision="blocked",
            )
            # Group by workflow → run → events
            grouped: dict = defaultdict(lambda: defaultdict(list))
            ungrouped = []
            for r in rows:
                wf = r.get("conductai_workflow_id") or r.get("workflow_id")
                run = r.get("conductai_run_id") or r.get("run_id")
                if wf and run:
                    grouped[wf][run].append(r)
                else:
                    ungrouped.append(r)
            if not grouped and not ungrouped:
                return {
                    "skill": "governance",
                    "ready": False,
                    "answer": "No workflow-triggered blocks found today.",
                }
            summary_rows = []
            for wf_id, runs in grouped.items():
                for run_id, events in runs.items():
                    summary_rows.append({
                        "workflow_id": wf_id,
                        "run_id": run_id,
                        "blocks": len(events),
                        "rules": ", ".join({e.get("rule_id") or "unknown" for e in events}),
                        "user_email": events[0].get("user_email", ""),
                        "ai_tool": events[0].get("ai_tool", ""),
                    })
            total = sum(r["blocks"] for r in summary_rows)
            return {
                "skill": "governance",
                "ready": False,
                "answer": f"{total} block(s) from {len(summary_rows)} workflow run(s) today.",
                "component": "WorkflowBlocksView",
                "drilldown": {"path": "/guard/activity", "filters": {"decision": "blocked"}},
                "columns": [
                    {"key": "workflow_id", "label": "Workflow",  "type": "text"},
                    {"key": "run_id",      "label": "Run",       "type": "text"},
                    {"key": "blocks",      "label": "Blocks",    "type": "number"},
                    {"key": "rules",       "label": "Rules",     "type": "text"},
                    {"key": "user_email",  "label": "User",      "type": "text"},
                    {"key": "ai_tool",     "label": "AI Tool",   "type": "text"},
                ],
                "rows": summary_rows,
            }

        if intent == "team_memory_feed":
            rows = executor._tool_get_team_memory_feed(limit=20)
            return {
                "skill": "memory",
                "ready": False,
                "answer": f"{len(rows)} team memory record(s)." if rows else "No team memory records yet.",
                "component": "MemoryResultsTable",
                "drilldown": {"path": "/guard/memory"},
                "columns": [
                    {"key": "summary",         "label": "Summary",   "type": "text"},
                    {"key": "developer_email", "label": "Developer", "type": "text"},
                    {"key": "topic_tags",      "label": "Tags",      "type": "text"},
                    {"key": "repo",            "label": "Repo",      "type": "text"},
                    {"key": "created_at",      "label": "Date",      "type": "date"},
                ],
                "rows": rows,
            }

        if intent == "session_reports_feed":
            rows = executor._tool_get_session_reports_feed(limit=20)
            return {
                "skill": "session",
                "ready": False,
                "answer": f"{len(rows)} session report(s)." if rows else "No session reports yet.",
                "component": "SessionResultsTable",
                "drilldown": {"path": "/guard/session-reports"},
                "columns": [
                    {"key": "summary",         "label": "Summary",   "type": "text"},
                    {"key": "developer_email", "label": "Developer", "type": "text"},
                    {"key": "ai_tool",         "label": "AI Tool",   "type": "text"},
                    {"key": "created_at",      "label": "Date",      "type": "date"},
                ],
                "rows": rows,
            }

    except Exception:
        return None  # fall through to agent
    return None
