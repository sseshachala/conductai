"""GLens Planner — decomposes complex questions into ordered subtasks."""
import json

from app.modules.glens.inference import chat as qwen_chat

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


def plan(question: str, last_answer: str | None = None) -> list[dict]:
    """
    Returns a list of subtasks: [{id, skill, question}]
    Falls back to single report subtask on any failure.
    """
    user_content = question
    if last_answer:
        user_content = f"[Previous answer: {last_answer}]\n\nUser follow-up: {question}"

    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = qwen_chat(messages)
        parsed = json.loads(raw)
        subtasks = parsed.get("subtasks", [])
        valid = [t for t in subtasks if t.get("skill") in _SKILLS and t.get("question")]
        return valid or [{"id": "1", "skill": "report", "question": question}]
    except Exception:
        return [{"id": "1", "skill": "report", "question": question}]
