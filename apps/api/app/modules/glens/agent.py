"""GLens Agent — loads skills at runtime, runs multi-turn tool-calling loop."""
import json
from collections.abc import Callable
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import structlog

from app.core.config import settings
from app.modules.glens.executor import Executor
from app.modules.glens.formatters import format_tool_result
from app.modules.glens.grounding import check_grounded
from app.modules.glens.inference import chat_with_tools, dispatch_tool

log = structlog.get_logger(__name__)

_SKILLS_DIR = Path(__file__).parent / "skills"
MAX_TOOL_ROUNDS = 5


def _load_skill_uncached(name: str) -> dict:
    d = _SKILLS_DIR / name
    if not d.exists():
        raise ValueError(f"GLens skill '{name}' not found at {d}")
    return {
        "name": name,
        "prompt": (d / "prompt.txt").read_text(),
        "tools": json.loads((d / "tools.json").read_text()),
    }

@lru_cache(maxsize=16)
def _load_skill_cached(name: str) -> dict:
    return _load_skill_uncached(name)

def _load_skill(name: str) -> dict:
    if getattr(settings, "environment", "production") != "production":
        return _load_skill_uncached(name)
    return _load_skill_cached(name)


_TOOL_STATUS: dict[str, str] = {
    "get_governance_kpis": "Fetching governance KPIs...",
    "get_spend_summary": "Loading spend data...",
    "get_blocked_events": "Retrieving blocked events...",
    "get_audit_events": "Loading audit log...",
    "get_agent_coverage": "Checking agent coverage...",
    "get_compliance_status": "Evaluating compliance controls...",
    "get_rules": "Loading Guard rules...",
    "search_memory": "Searching team memory...",
    "search_sessions": "Searching session reports...",
    "export_csv": "Preparing export...",
}


def _tool_status(tool_name: str) -> str:
    return _TOOL_STATUS.get(tool_name, f"Running {tool_name}...")


def _build_system(skills: list[dict]) -> str:
    if len(skills) == 1:
        return skills[0]["prompt"]
    parts = [f"[{s['name'].upper()} SKILL]\n{s['prompt']}" for s in skills]
    return "\n\n---\n\n".join(parts)


class Agent:
    def __init__(self, skill_names: list[str]):
        # presenter always loads last — owns all rendering conventions
        all_names = [n for n in skill_names if n != "presenter"] + ["presenter"]
        self.skills = [_load_skill(n) for n in all_names]
        self.system = _build_system(self.skills)
        self.tools = [t for s in self.skills for t in s["tools"]]
        seen: dict[str, bool] = {}
        for t in self.tools:
            name = t["function"]["name"]
            if name in seen:
                log.warning("glens.agent.tool_name_collision", tool=name)
            seen[name] = True

    def run(
        self,
        messages: list[dict],
        executor: Executor,
        on_event: Callable[[dict], None] | None = None,
    ) -> dict:
        # Fast path: 1 LLM call (dispatch) → Python formats result → done
        user_msg = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        try:
            tool_name, args = dispatch_tool(user_msg)
            if on_event:
                on_event({"type": "thinking", "label": _tool_status(tool_name)})
            import json as _json
            raw = executor.call(tool_name, _json.dumps(args))
            result = _json.loads(raw)
            formatted = format_tool_result(tool_name, result)
            if formatted is not None:
                log.debug("glens.agent.dispatch_hit", tool=tool_name)
                return formatted
        except Exception as e:
            log.debug("glens.agent.dispatch_miss", error=str(e))
            # Fall through to multi-turn agent below

        # Slow path: multi-turn tool-calling loop (complex/unsupported queries)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        system = f"Today is {today} (UTC).\n\n{self.system}"
        loop_msgs = [{"role": "system", "content": system}] + list(messages[-20:])
        collected_tool_results: list = []

        for round_num in range(MAX_TOOL_ROUNDS):
            msg = chat_with_tools(loop_msgs, self.tools)

            if not msg.tool_calls:
                # Final answer
                return self._finalize(msg.content, collected_tool_results)

            # Append assistant turn with tool calls (content may be None per OpenAI spec)
            loop_msgs.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })

            # Execute each tool call and feed results back
            for tc in msg.tool_calls:
                if on_event:
                    on_event({"type": "thinking", "label": _tool_status(tc.function.name)})
                result = executor.call(tc.function.name, tc.function.arguments)
                log.debug("glens.agent.tool_executed", tool=tc.function.name, round=round_num)
                try:
                    collected_tool_results.append(json.loads(result))
                except json.JSONDecodeError:
                    collected_tool_results.append(result)
                loop_msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        # Exceeded max rounds — force final answer without tools
        log.warning("glens.agent.max_rounds_exceeded", skill=self.skills[0]["name"])
        loop_msgs.append({"role": "user", "content": "Please give your final answer now."})
        msg = chat_with_tools(loop_msgs, self.tools)
        return self._finalize(msg.content, collected_tool_results, default_msg="Could not generate answer.")

    def _finalize(self, content: str | None, tool_results: list, default_msg: str | None = None) -> dict:
        """Parse the model's final message and run the (non-blocking) groundedness check."""
        skill_name = self.skills[0]["name"]
        try:
            parsed = json.loads(content or "{}")
        except json.JSONDecodeError:
            return {"skill": skill_name, "ready": False, "answer": content or default_msg}

        answer = parsed.get("answer") if isinstance(parsed, dict) else None
        if answer:
            check_grounded(answer, tool_results, skill=parsed.get("skill", skill_name))
        return parsed
