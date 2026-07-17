"""GLens Router — classifies user intent into one or more skill names."""
import json
from pathlib import Path

from app.modules.glens.inference import chat as qwen_chat

_SKILLS = ["report", "analytics", "extract", "memory", "session"]

_PROMPT = f"""You are a routing classifier for GLens, a governance assistant.

Given a user question, return which skills are needed to answer it.

SKILLS:
  report    — build a dashboard (KPIs, charts, tables) from spend/events data
  analytics — answer trend, comparison, or aggregation questions with numbers
  extract   — export data to CSV or produce a downloadable summary
  memory    — search team memory for decisions, policy rationale, context
  session   — search session reports for specific agent runs or developer activity

RULES:
- Return only skills actually needed
- Most questions need exactly one skill
- "show me" or "build a view" → report
- "how many", "compare", "trend", "which rule" → analytics
- "export", "download", "CSV" → extract
- "team decided", "why was this policy", "what did we agree" → memory
- "session", "agent run", "what did the agent do" → session

Respond with ONLY valid JSON:
{{"skills": ["skill1"]}}

Valid skill names: {", ".join(_SKILLS)}
"""


def route(question: str) -> list[str]:
    """Return list of skill names needed to answer the question."""
    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        raw = qwen_chat(messages)
        parsed = json.loads(raw)
        skills = [s for s in parsed.get("skills", []) if s in _SKILLS]
        return skills or ["report"]  # ponytail: fallback to report
    except Exception:
        return ["report"]
