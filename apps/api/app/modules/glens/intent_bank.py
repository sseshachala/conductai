"""Labeled intent examples for semantic routing."""
from __future__ import annotations

# intent → list of example phrases (varied phrasings)
INTENT_EXAMPLES: dict[str, list[str]] = {
    "governance_kpis": [
        "governance overview", "how are we doing", "dashboard summary",
        "risk avoided", "blocks this month", "governance summary", "kpi",
    ],
    "governance_activity": [
        "show me events", "what happened today", "recent activity",
        "show activity", "what events occurred", "audit log",
    ],
    "governance_blocked": [
        "show blocks", "who got blocked", "blocked requests",
        "how many blocks", "show me blocks", "blocked events",
        "how many blocked", "blocks in june", "blocks this week",
    ],
    "governance_warned": [
        "who was warned", "warnings today", "show warnings",
        "warned events", "how many warnings",
    ],
    "workflow_blocks": [
        "workflow blocks", "which workflows triggered", "automation blocks",
        "blocks from workflows", "workflow triggered block",
    ],
    "correlated_activity": [
        "what was the user doing when blocked", "correlated events",
        "session context for block", "relate block to session",
    ],
    "spend_summary": [
        "show spend", "cost this month", "budget usage",
        "how much spent", "token cost", "llm spend",
    ],
    "list_policies": [
        "list rules", "show policies", "guard rules",
        "what rules exist", "active policies", "list guard rules",
    ],
    "discovery_summary": [
        "discovered agents", "agent coverage", "which agents are registered",
        "agent inventory", "how many agents",
    ],
    "compliance_status": [
        "compliance status", "SOC2 coverage", "OWASP compliance",
        "framework coverage", "how compliant are we",
    ],
    "framework_coverage": [
        "which frameworks are installed", "compliance framework breakdown",
        "framework coverage by pack", "list installed frameworks",
        "what compliance packs do we have",
    ],
    "get_guard_config": [
        "guard config", "guard settings", "is guard enabled",
        "guard status", "what is guard configured to do",
    ],
    "get_budgets": [
        "budget limits", "spend limits", "token budget",
        "what are the budgets", "budget thresholds",
    ],
    "search_memory": [
        "team memory", "what did we decide", "past decisions",
        "search team memory", "recall decision", "what was agreed",
    ],
    "search_sessions": [
        "search sessions", "find session about", "session reports",
        "past sessions", "session history",
    ],
    "create_guard_rule": [
        "create a rule", "add a rule", "new guard rule",
        "block this pattern", "add policy", "create policy",
    ],
    "edit_guard_rule": [
        "edit rule", "update rule", "make rule stricter",
        "disable rule", "enable rule", "modify rule", "change rule",
    ],
    "delete_guard_rule": [
        "delete rule", "remove rule", "delete that rule", "remove policy",
    ],
}

# maps intent → tool name used by executor
INTENT_TO_TOOL: dict[str, str] = {
    "governance_kpis":       "get_governance_kpis",
    "governance_activity":   "get_recent_governance_events",
    "governance_blocked":    "get_recent_governance_events",
    "governance_warned":     "get_recent_governance_events",
    "workflow_blocks":       "get_recent_governance_events",
    "correlated_activity":   "get_recent_governance_events",
    "spend_summary":         "get_spend_summary",
    "list_policies":         "list_policies",
    "discovery_summary":     "get_discovery_summary",
    "compliance_status":     "get_compliance_status",
    "framework_coverage":    "get_framework_coverage",
    "get_guard_config":      "get_guard_config",
    "get_budgets":           "get_budgets",
    "search_memory":         "search_memory",
    "search_sessions":       "search_sessions",
    "create_guard_rule":     "create_guard_rule",
    "edit_guard_rule":       "edit_guard_rule",
    "delete_guard_rule":     "delete_guard_rule",
}

# write tools that need confirmation before execution
WRITE_INTENTS = {"create_guard_rule", "edit_guard_rule", "delete_guard_rule"}
