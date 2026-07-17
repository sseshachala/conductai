"""GLens Planner — decomposes complex questions into ordered subtasks."""
import json

import structlog

from app.modules.glens.inference import chat as qwen_chat
from app.modules.glens.utils import extract_json

log = structlog.get_logger(__name__)


_SKILLS = ["report", "analytics", "extract", "memory", "session", "rules", "guard_config", "spend_config", "discovery", "compliance", "governance"]

_PROMPT = f"""You are a task planner for GLens, a governance analytics assistant.

Given a user question, decompose it into one or more subtasks.
Each subtask has a skill and a focused sub-question.

SKILLS:
  report      — build a dashboard (KPIs, charts, tables)
  analytics   — answer trend, comparison, aggregation questions with numbers
  extract     — export data to CSV or produce a downloadable summary
  memory      — search team memory for decisions, policy context
  session     — search session reports for specific agent runs
  rules       — read, create, or update individual Guard block/warn/audit rules
  guard_config — configure Guard settings (enforcement mode, fail mode, persona, Slack, advisory)
  spend_config — configure workspace, developer, and tool-level spend budgets
  discovery   — agents discovered in the workspace: coverage %, risk scores, framework breakdown, which agents are under/not under Guard
  compliance  — OWASP Agentic Top 10 control status, governance grade (A-F), score, 24h blocked/event counts
  governance  — governance KPIs (events today, blocks today, active developers, MTD blocks, risk avoided), installed compliance frameworks, recent audit events

RULES:
- Simple questions → one subtask
- Multi-part questions → multiple subtasks, one per distinct intent
- Preserve the user's original phrasing in each sub-question
- Order subtasks logically (fetch before export, analyze before summarize)

Respond with ONLY valid JSON:
{{"subtasks": [{{"id": "1", "skill": "report", "question": "focused sub-question"}}]}}

Valid skill names: {", ".join(_SKILLS)}
"""

_PAGE_CONTEXT_SKILL = {
    "activity": "governance",
    "chat": "analytics",
    "compliance": "compliance",
    "discovery": "discovery",
    "governance": "governance",
    "policies": "rules",
    "spend": "analytics",
}


def plan(
    question: str,
    last_answer: str | None = None,
    page_context: str | None = None,
    context_summary: str | None = None,
) -> list[dict]:
    """
    Returns a list of subtasks: [{id, skill, question}]
    Falls back to single report subtask on any failure.
    """
    user_content = question
    if context_summary:
        user_content = f"[Conversation summary: {context_summary}]\n\n{user_content}"
    if page_context:
        user_content = f"[User is on the '{page_context}' page]\n\n{user_content}"
    if last_answer:
        user_content = f"[Previous answer: {last_answer}]\n\nUser follow-up: {user_content}"

    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = qwen_chat(messages)
        parsed = json.loads(extract_json(raw))
        subtasks = parsed.get("subtasks", [])
        valid = [t for t in subtasks if t.get("skill") in _SKILLS and t.get("question")]
        if valid:
            return valid
        log.warning("glens.planner.no_valid_subtasks", raw=raw[:200])
    except Exception as e:
        log.warning("glens.planner.parse_failed", error=str(e), raw=raw[:200] if "raw" in dir() else "")

    # Fallback: guess skill from page context first, then question keywords
    q = question.lower()
    skill = _PAGE_CONTEXT_SKILL.get(page_context or "", "analytics")
    if any(w in q for w in ["cost", "spend", "token", "budget"]):
        skill = "analytics"
    elif any(w in q for w in ["block", "warn", "event", "who", "recent", "list"]):
        skill = "governance"
    elif any(w in q for w in ["rule", "policy", "create", "disable", "enable"]):
        skill = "rules"
    elif any(w in q for w in ["agent", "discover", "coverage"]):
        skill = "discovery"
    elif any(w in q for w in ["compliance", "grade", "owasp"]):
        skill = "compliance"
    elif any(w in q for w in ["memory", "worked on", "decision history"]):
        skill = "memory"
    elif any(w in q for w in ["session report", "autonomy", "developer productivity"]):
        skill = "session"
    elif any(w in q for w in ["csv", "export", "download"]):
        skill = "extract"
    return [{"id": "1", "skill": skill, "question": question}]
