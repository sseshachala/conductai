"""Intent shortcuts — bypass LLM inference for deterministic queries.

Pattern match → call executor → return formatted JSON.
Eliminates 2 LLM round-trips (~7s) for common governance questions.
"""
import re
from collections import Counter
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


# Each entry: (regex, handler_fn(msg, executor) -> dict | None)
# Return None to fall through to the full agent pipeline.
_SHORTCUTS: list[tuple[str, ...]] = [
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
        if intent == "governance_activity":
            rows = executor._tool_get_recent_governance_events(since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows),
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
        if intent == "governance_blocked":
            rows = executor._tool_get_recent_governance_events(decision="blocked", since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows, "blocks"),
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
        if intent == "governance_warned":
            rows = executor._tool_get_recent_governance_events(decision="warned", since=today, limit=20)
            return {
                "skill": "governance",
                "ready": False,
                "answer": _decision_summary(rows, "warnings"),
                "columns": _ACTIVITY_COLUMNS,
                "rows": rows,
            }
    except Exception:
        return None  # fall through to agent
    return None
