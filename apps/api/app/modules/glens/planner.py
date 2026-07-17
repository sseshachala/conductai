"""GLens Planner — decomposes complex questions into ordered subtasks."""
import json

from app.modules.glens.inference import chat as qwen_chat

_SKILLS = ["report", "analytics", "extract", "memory", "session"]

_PROMPT = f"""You are a task planner for GLens, a governance analytics assistant.

Given a user question, decompose it into one or more subtasks.
Each subtask has a skill and a focused sub-question.

SKILLS:
  report    — build a dashboard (KPIs, charts, tables)
  analytics — answer trend, comparison, aggregation questions with numbers
  extract   — export data to CSV or produce a downloadable summary
  memory    — search team memory for decisions, policy context
  session   — search session reports for specific agent runs

RULES:
- Simple questions → one subtask
- Multi-part questions → multiple subtasks, one per distinct intent
- Preserve the user's original phrasing in each sub-question
- Order subtasks logically (fetch before export, analyze before summarize)

Respond with ONLY valid JSON:
{{"subtasks": [{{"id": "1", "skill": "report", "question": "focused sub-question"}}]}}

Valid skill names: {", ".join(_SKILLS)}
"""


def plan(question: str) -> list[dict]:
    """
    Returns a list of subtasks: [{id, skill, question}]
    Falls back to single report subtask on any failure.
    """
    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        raw = qwen_chat(messages)
        parsed = json.loads(raw)
        subtasks = parsed.get("subtasks", [])
        valid = [t for t in subtasks if t.get("skill") in _SKILLS and t.get("question")]
        return valid or [{"id": "1", "skill": "report", "question": question}]
    except Exception:
        return [{"id": "1", "skill": "report", "question": question}]
