"""GLens system prompt — model picks components from an allowed menu."""
from datetime import date

VALID_KPIS = [
    "events_today",
    "blocked_today",
    "total_cost_usd",
    "active_developers",
    "tokens_saved_today",
    "total_tokens_before",
    "total_tokens_after",
    "hook_sessions",
]

VALID_CHARTS = ["by_ai_tool", "by_developer"]

VALID_TABLES = ["blocked_events", "warned_events", "allowed_events", "recent_sessions"]

KPI_META = {
    "events_today":        {"label": "Events Today",          "field": "events_today"},
    "blocked_today":       {"label": "Blocks Today",          "field": "blocked_today"},
    "total_cost_usd":      {"label": "Total Cost (month)",    "field": "total_cost_usd"},
    "active_developers":   {"label": "Active Developers",     "field": "active_developers"},
    "tokens_saved_today":  {"label": "Tokens Saved Today",    "field": "tokens_saved_today"},
    "total_tokens_before": {"label": "Tokens Before (month)", "field": "total_tokens_before"},
    "total_tokens_after":  {"label": "Tokens After (month)",  "field": "total_tokens_after"},
    "hook_sessions":       {"label": "Hook Sessions",         "field": "hook_sessions"},
}

CHART_META = {
    "by_ai_tool":   {"title": "Cost by AI Tool",   "field": "by_ai_tool",   "x": "ai_tool",    "y": "cost_usd"},
    "by_developer": {"title": "Cost by Developer", "field": "by_developer", "x": "user_email", "y": "cost_usd"},
}

TABLE_META = {
    "blocked_events":  {"title": "Recent Blocks",   "endpoint": "/guard/events",         "params": {"decision": "blocked", "limit": 20}},
    "warned_events":   {"title": "Recent Warnings", "endpoint": "/guard/events",         "params": {"decision": "warned",  "limit": 20}},
    "allowed_events":  {"title": "Recent Allows",   "endpoint": "/guard/events",         "params": {"decision": "allowed", "limit": 20}},
    "recent_sessions": {"title": "Recent Sessions", "endpoint": "/guard/spend/sessions", "params": {"limit": 20}},
}


def build_system_prompt() -> str:
    today = date.today().isoformat()
    kpi_list    = ", ".join(VALID_KPIS)
    chart_list  = ", ".join(VALID_CHARTS)
    table_list  = ", ".join(VALID_TABLES)
    return f"""You are GLens, a governance assistant for ConductAI.
Today's date is {today}.

You help users explore their AI governance data. Respond with JSON only.

AVAILABLE COMPONENTS — pick only what fits the user's question:

KPIs (from spend summary):
  events_today        — total tool calls logged today
  blocked_today       — tool calls blocked today
  total_cost_usd      — total AI spend this month
  active_developers   — developers active today
  tokens_saved_today  — tokens saved by Guard today
  total_tokens_before — total tokens used before Guard (month)
  total_tokens_after  — total tokens used after Guard (month)
  hook_sessions       — hook sessions count

Charts (cost breakdowns):
  by_ai_tool   — bar chart: cost by AI tool
  by_developer — bar chart: cost by developer

Tables (event lists):
  blocked_events  — recent blocked tool calls
  warned_events   — recent warned tool calls
  allowed_events  — recent allowed tool calls
  recent_sessions — recent agent sessions with spend

RULES:
- Pick only components relevant to the question
- Do not invent component names — use only those listed above
- month: use YYYY-MM format; default to current month if not specified
- If the question is about blocks/policy → pick blocked_today, blocked_events
- If the question is about spend/cost → pick total_cost_usd, by_ai_tool, by_developer
- If the question is about activity/usage → pick events_today, active_developers, recent_sessions
- If the question is broad/overview → pick a balanced set across all areas

When ready, respond with ONLY:
{{"ready": true, "title": "...", "month": "YYYY-MM", "kpis": [{kpi_list!r}...], "charts": [...], "tables": [...]}}

Valid values:
  kpis:   [{kpi_list}]
  charts: [{chart_list}]
  tables: [{table_list}]

If you need clarification:
{{"ready": false, "question": "One short clarifying question"}}"""
