"""Pure-Python formatters — turn raw executor results into frontend-ready JSON.

Called after dispatch_tool() runs the DB query. Zero LLM calls.
"""
from collections import Counter

_ACTIVITY_COLUMNS = [
    {"key": "ts",         "label": "Time",     "type": "date"},
    {"key": "decision",   "label": "Decision", "type": "badge"},
    {"key": "rule_id",    "label": "Rule",     "type": "text"},
    {"key": "ai_tool",    "label": "AI Tool",  "type": "text"},
    {"key": "user_email", "label": "User",     "type": "text"},
]


def _count_summary(rows: list[dict], noun: str = "events") -> str:
    if not rows:
        return f"No {noun} found."
    counts = Counter(r.get("decision", "allowed") for r in rows)
    parts = [f"{v} {k}" for k, v in counts.most_common()]
    return f"{len(rows)} {noun} — {', '.join(parts)}."


def format_tool_result(tool: str, result) -> dict | None:
    """Return formatted payload or None to fall back to the full agent."""
    if tool == "get_recent_governance_events":
        rows = result if isinstance(result, list) else result.get("rows", [])
        return {
            "skill": "governance",
            "ready": False,
            "answer": _count_summary(rows),
            "component": "ActivityTable",
            "drilldown": {"path": "/guard/activity"},
            "columns": _ACTIVITY_COLUMNS,
            "rows": rows,
        }

    if tool == "get_governance_kpis":
        if not isinstance(result, dict):
            return None
        kpis = [
            {"label": "Events Today",        "value": result.get("events_today", 0)},
            {"label": "Blocked Today",        "value": result.get("blocked_today", 0)},
            {"label": "Active Developers",    "value": result.get("active_developers_today", 0)},
            {"label": "Blocks (MTD)",         "value": result.get("blocks_mtd", 0)},
            {"label": "Risk Avoided (MTD)",   "value": f"${result.get('risk_avoided_usd_mtd', 0):,.2f}"},
        ]
        n = result.get("events_today", 0)
        b = result.get("blocked_today", 0)
        return {
            "skill": "governance",
            "ready": True,
            "title": "Governance Overview",
            "answer": f"{n} events today, {b} blocked.",
            "component": "GovernanceKpiCards",
            "drilldown": {"path": "/guard"},
            "kpis": kpis,
            "charts": [],
            "tables": [],
        }

    if tool == "get_spend_summary":
        if not isinstance(result, dict):
            return None
        dev_cols = [
            {"key": "email",    "label": "Developer", "type": "text"},
            {"key": "cost_usd", "label": "Cost (USD)", "type": "currency"},
        ]
        rows = result.get("by_developer", [])
        total = result.get("total_cost_usd", 0)
        return {
            "skill": "analytics",
            "ready": False,
            "answer": f"Total spend: ${total:,.4f}. {len(rows)} developer(s) active.",
            "component": "SpendDashboard",
            "drilldown": {"path": "/guard/spend"},
            "columns": dev_cols,
            "rows": rows,
        }

    if tool == "list_policies":
        rows = result if isinstance(result, list) else []
        cols = [
            {"key": "rule_id",     "label": "Rule ID",  "type": "text"},
            {"key": "description", "label": "Description", "type": "text"},
            {"key": "decision",    "label": "Action",   "type": "badge"},
            {"key": "enabled",     "label": "Enabled",  "type": "boolean"},
        ]
        return {
            "skill": "rules",
            "ready": False,
            "answer": f"{len(rows)} Guard rule(s) configured.",
            "component": "PoliciesTable",
            "drilldown": {"path": "/guard/policies"},
            "columns": cols,
            "rows": rows,
        }

    if tool == "get_compliance_status":
        if not isinstance(result, dict):
            return None
        score = result.get("overall_score", 0)
        controls = result.get("controls", [])
        cols = [
            {"key": "framework", "label": "Framework", "type": "text"},
            {"key": "status",    "label": "Status",    "type": "badge"},
            {"key": "score",     "label": "Score",     "type": "percent"},
        ]
        return {
            "skill": "compliance",
            "ready": False,
            "answer": f"Overall compliance score: {score}%. {len(controls)} control(s) evaluated.",
            "component": "CompliancePacksTable",
            "drilldown": {"path": "/guard/compliance"},
            "columns": cols,
            "rows": controls,
        }

    if tool == "get_discovery_summary":
        if not isinstance(result, dict):
            return None
        total = result.get("total_agents", 0)
        covered = result.get("covered", 0)
        return {
            "skill": "discovery",
            "ready": False,
            "answer": f"{covered} of {total} agents under Guard coverage.",
            "component": "AgentsTable",
            "drilldown": {"path": "/guard/discover"},
            "columns": [
                {"key": "name",    "label": "Agent",    "type": "text"},
                {"key": "tool",    "label": "AI Tool",  "type": "text"},
                {"key": "covered", "label": "Covered",  "type": "boolean"},
            ],
            "rows": result.get("agents", []),
        }

    # Unknown tool or complex result — fall back to full agent
    return None
