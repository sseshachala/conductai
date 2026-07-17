"""GLens Agent — loads skills at runtime, runs multi-turn tool-calling loop."""
import json
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import structlog

from app.modules.glens.executor import Executor
from app.modules.glens.inference import chat_with_tools

log = structlog.get_logger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
MAX_TOOL_ROUNDS = 5


@lru_cache(maxsize=16)
def _load_skill(name: str) -> dict:
    d = _SKILLS_DIR / name
    if not d.exists():
        raise ValueError(f"GLens skill '{name}' not found at {d}")
    return {
        "name": name,
        "prompt": (d / "prompt.txt").read_text(),
        "tools": json.loads((d / "tools.json").read_text()),
    }


def _build_system(skills: list[dict]) -> str:
    if len(skills) == 1:
        return skills[0]["prompt"]
    parts = [f"[{s['name'].upper()} SKILL]\n{s['prompt']}" for s in skills]
    return "\n\n---\n\n".join(parts)


class Agent:
    def __init__(self, skill_names: list[str]):
        self.skills = [_load_skill(n) for n in skill_names]
        self.system = _build_system(self.skills)
        self.tools = [t for s in self.skills for t in s["tools"]]

    def run(self, messages: list[dict], executor: Executor) -> dict:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system = f"Today is {today} (UTC).\n\n{self.system}"
        loop_msgs = [{"role": "system", "content": system}] + list(messages[-20:])

        for round_num in range(MAX_TOOL_ROUNDS):
            msg = chat_with_tools(loop_msgs, self.tools)

            if not msg.tool_calls:
                # Final answer
                try:
                    return json.loads(msg.content or "{}")
                except json.JSONDecodeError:
                    return {"skill": self.skills[0]["name"], "ready": False, "answer": msg.content}

            # Append assistant turn with tool calls
            loop_msgs.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })

            # Execute each tool call and feed results back
            for tc in msg.tool_calls:
                result = executor.call(tc.function.name, tc.function.arguments)
                log.debug("glens.agent.tool_executed", tool=tc.function.name, round=round_num)
                loop_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # Exceeded max rounds — force final answer without tools
        log.warning("glens.agent.max_rounds_exceeded", skill=self.skills[0]["name"])
        loop_msgs.append({"role": "user", "content": "Please give your final answer now."})
        msg = chat_with_tools(loop_msgs, self.tools)
        try:
            return json.loads(msg.content or "{}")
        except json.JSONDecodeError:
            return {"skill": self.skills[0]["name"], "ready": False, "answer": msg.content or "Could not generate answer."}
