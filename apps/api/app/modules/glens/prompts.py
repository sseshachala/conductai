"""GLens prompt loader — text lives in prompts/*.txt, metadata dicts live here."""
import json
from datetime import date
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_SYSTEM_TEMPLATE = (_PROMPTS_DIR / "system.txt").read_text()
_CONTEXT_TEMPLATE = (_PROMPTS_DIR / "context.txt").read_text()

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
    return (
        _SYSTEM_TEMPLATE
        .replace("{today}", date.today().isoformat())
        .replace("{kpi_list}", ", ".join(VALID_KPIS))
        .replace("{chart_list}", ", ".join(VALID_CHARTS))
        .replace("{table_list}", ", ".join(VALID_TABLES))
    )


def build_context_messages(guard_ctx: dict) -> list[dict]:
    """Inject live Guard snapshot as a user/assistant pair before the user's question."""
    content = _CONTEXT_TEMPLATE.replace("{guard_ctx}", json.dumps(guard_ctx))
    return [
        {"role": "user", "content": content},
        {"role": "assistant", "content": "Understood, I have the current Guard data."},
    ]
