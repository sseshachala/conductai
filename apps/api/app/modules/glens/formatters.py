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

    if tool == "search_memory":
        rows = result if isinstance(result, list) else []
        if isinstance(result, dict) and "error" in result:
            return {
                "skill": "memory", "ready": False,
                "answer": "Team memory search requires embeddings to be configured for this workspace.",
                "component": "MemoryResultsTable", "rows": [], "columns": [],
            }
        return {
            "skill": "memory",
            "ready": False,
            "answer": f"{len(rows)} team memory result(s) found." if rows else "No confident team memory match found for that query.",
            "component": "MemoryResultsTable",
            "drilldown": {"path": "/guard/memory"},
            "columns": [
                {"key": "summary",          "label": "Summary",    "type": "text"},
                {"key": "developer_email",  "label": "Developer",  "type": "text"},
                {"key": "topic_tags",       "label": "Tags",       "type": "text"},
                {"key": "repo",             "label": "Repo",       "type": "text"},
                {"key": "created_at",       "label": "Date",       "type": "date"},
                {"key": "score",            "label": "Relevance",  "type": "number"},
            ],
            "rows": rows,
        }

    if tool == "search_sessions":
        rows = result if isinstance(result, list) else []
        if isinstance(result, dict) and "error" in result:
            return {
                "skill": "session", "ready": False,
                "answer": "Session search requires embeddings to be configured for this workspace.",
                "component": "SessionResultsTable", "rows": [], "columns": [],
            }
        return {
            "skill": "session",
            "ready": False,
            "answer": f"{len(rows)} session report(s) found." if rows else "No confident session report match found for that query.",
            "component": "SessionResultsTable",
            "drilldown": {"path": "/guard/session-reports"},
            "columns": [
                {"key": "summary",         "label": "Summary",    "type": "text"},
                {"key": "developer_email", "label": "Developer",  "type": "text"},
                {"key": "ai_tool",         "label": "AI Tool",    "type": "text"},
                {"key": "created_at",      "label": "Date",       "type": "date"},
                {"key": "score",           "label": "Relevance",  "type": "number"},
            ],
            "rows": rows,
        }

    if tool == "create_guard_rule":
        if not isinstance(result, dict):
            return None
        desc = result.get("description", "").strip()
        match_tool = result.get("match_tool") or ""
        match_pattern = result.get("match_pattern") or ""
        # Vague description — too short or single verb
        if len(desc) < 10 or len(desc.split()) < 2:
            return _clarify(
                "I need a clearer description to create this rule. What should it block or warn on?",
                ["Block .env file access for all tools",
                 "Warn when Claude writes to config files",
                 "Block cursor from reading secrets directories"],
            )
        # Catch-all: both match_tool and match_pattern are empty/wildcard — would fire on everything
        needs_generate = (not match_pattern) and (not match_tool or match_tool == "*")
        if needs_generate:
            # Signal to T3 to call the generate endpoint — formatter can't make API calls
            return {"_needs_generate": True, "description": desc, "action": result.get("action", "block")}
        action = result.get("action", "block")
        rule_id = result.get("rule_id") or _slugify(desc)
        draft = {
            "rule_id": rule_id,
            "description": desc,
            "action": action,
            "match_tool": match_tool or "*",
            "match_pattern": match_pattern,
            "severity": result.get("severity", "medium"),
        }
        return {
            "skill": "rules",
            "ready": False,
            "confirm_required": True,
            "action": "create",
            "answer": f"Create a new **{action}** rule: {desc}",
            "draft": draft,
            "mapping": [
                {"field": "rule_id",       "column": "rule_id",      "description": "Unique rule identifier",       "value": rule_id},
                {"field": "description",   "column": "description",  "description": "What this rule does",          "value": desc},
                {"field": "action",        "column": "action",       "description": "block / warn / audit",         "value": action},
                {"field": "match_tool",    "column": "match_tool",   "description": "AI tool this applies to",      "value": match_tool or "*"},
                {"field": "match_pattern", "column": "match_pattern","description": "Regex matched against prompt", "value": match_pattern},
                {"field": "severity",      "column": "severity",     "description": "Alert severity",               "value": result.get("severity", "medium")},
            ],
        }

    if tool == "edit_guard_rule":
        if not isinstance(result, dict):
            return None
        rule_id = result.get("rule_id", "").strip()
        if not rule_id:
            return _clarify(
                "Which rule should I update? Say 'list rules' to see your active rules, then say 'edit rule [rule_id]'.",
                ["List my guard rules", "Disable rule cursor-block-env", "Change rule X to warn instead of block"],
            )
        warning = result.get("_warning")
        changes = {k: v for k, v in result.items() if k not in ("rule_id", "_warning") and v is not None}
        if not changes:
            return _clarify(
                f"What should I change about rule **{rule_id}**? You can update its action, description, severity, or enable/disable it.",
                [f"Disable rule {rule_id}", f"Change rule {rule_id} to warn", f"Update description for rule {rule_id}"],
            )
        return {
            "skill": "rules",
            "ready": False,
            "confirm_required": True,
            "action": "patch",
            "answer": f"Edit rule **{rule_id}**: {', '.join(f'{k}={v}' for k, v in changes.items())}",
            "draft": changes,
            "target_rule_id": rule_id,
            "mapping": [{"field": k, "column": k, "description": "", "value": str(v)} for k, v in changes.items()],
            "warning": warning,
        }

    if tool == "delete_guard_rule":
        if not isinstance(result, dict):
            return None
        rule_id = result.get("rule_id", "").strip()
        if not rule_id:
            return _clarify(
                "Which rule should I delete? Say 'list rules' to see your active rules, then say 'delete rule [rule_id]'.",
                ["List my guard rules", "Delete rule cursor-block-env", "Remove the .env block rule"],
            )
        warning = result.get("_warning")
        return {
            "skill": "rules",
            "ready": False,
            "confirm_required": True,
            "action": "delete",
            "answer": f"Delete rule **{rule_id}**. This cannot be undone.",
            "draft": {"rule_id": rule_id},
            "target_rule_id": rule_id,
            "mapping": [{"field": "rule_id", "column": "rule_id", "description": "Rule to delete", "value": rule_id}],
            "warning": warning,
        }

    # Unknown tool or complex result — fall back to full agent
    return None


def _clarify(answer: str, suggestions: list[str]) -> dict:
    return {
        "skill": "rules",
        "ready": False,
        "clarification_required": True,
        "answer": answer,
        "followups": suggestions,
    }


def _slugify(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "custom_rule"
