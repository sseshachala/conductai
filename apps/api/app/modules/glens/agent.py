"""GLens Agent — loads skills at runtime and runs inference."""
import json
from pathlib import Path

from functools import lru_cache

from app.modules.glens.inference import chat as qwen_chat

_SKILLS_DIR = Path(__file__).parent / "skills"


@lru_cache(maxsize=16)
def _load_skill(name: str) -> dict:
    d = _SKILLS_DIR / name
    return {
        "name": name,
        "prompt": (d / "prompt.txt").read_text(),
        "tools": json.loads((d / "tools.json").read_text()),
        "resources": json.loads((d / "resources.json").read_text()),
    }


def _build_system(skills: list[dict]) -> str:
    """Merge prompts from all loaded skills into one system message."""
    if len(skills) == 1:
        return skills[0]["prompt"]
    parts = [f"[{s['name'].upper()} SKILL]\n{s['prompt']}" for s in skills]
    return "\n\n---\n\n".join(parts)


class Agent:
    def __init__(self, skill_names: list[str]):
        self.skills = [_load_skill(n) for n in skill_names]
        self.system = _build_system(self.skills)

    def run(self, messages: list[dict], context: dict) -> dict:
        """
        messages: conversation history (user + assistant turns)
        context:  live Guard data snapshot fetched by the router layer
        """
        ctx_block = {
            "role": "user",
            "content": f"[LIVE DATA]\n{json.dumps(context)}",
        }
        ack_block = {
            "role": "assistant",
            "content": "Understood, I have the current Guard data.",
        }
        system_msg = {"role": "system", "content": self.system}
        inference_msgs = [system_msg, ctx_block, ack_block] + messages[-20:]

        raw = qwen_chat(inference_msgs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # ponytail: non-JSON fallback — treat as plain answer
            return {"skill": self.skills[0]["name"], "ready": False, "answer": raw}
