"""
Anthropic LLMClient adapter.

Handles:
- Prompt caching via cache_system flag (ephemeral cache_control on system block)
- Tool use normalization (Anthropic tool_use content blocks -> LLMToolUseBlock)
- stop_reason passthrough (Anthropic already uses "end_turn" / "tool_use" / "max_tokens")
- Per-model cost computation from pricing table
- Conversation history formatting (Anthropic requires raw content objects for assistant turns)
"""
from __future__ import annotations

from typing import Any

from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage
from app.runtime.pricing import get_model_rates


def _anthropic_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("anthropic", model, pricing_snapshot)
    return round((
        usage.input_tokens         * rates["input"]
        + usage.output_tokens      * rates["output"]
        + usage.cache_read_tokens  * rates.get("cache_read", 0)
        + usage.cache_write_tokens * rates.get("cache_write", 0)
    ) / 1_000_000, 6)


class AnthropicClient:
    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None, base_url: str | None = None, default_headers: dict | None = None) -> None:
        import anthropic as _anthropic
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url is not None:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        self._client = _anthropic.Anthropic(**kwargs)
        self._pricing_snapshot = pricing_snapshot

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        cache_system: bool = False,
    ) -> LLMResponse:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if cache_system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            kwargs["extra_headers"] = {"anthropic-beta": "prompt-caching-2024-07-31"}
        else:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        raw = self._client.messages.create(**kwargs)

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        for block in raw.content:
            if block.type == "text":
                content.append(LLMTextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(LLMToolUseBlock(
                    id=block.id,
                    name=block.name,
                    input=dict(block.input) if block.input else {},
                ))

        u = getattr(raw, "usage", None)
        usage = LLMUsage(
            input_tokens=getattr(u, "input_tokens", 0),
            output_tokens=getattr(u, "output_tokens", 0),
            cache_read_tokens=getattr(u, "cache_read_input_tokens", 0),
            cache_write_tokens=getattr(u, "cache_creation_input_tokens", 0),
        )

        return LLMResponse(
            content=content,
            stop_reason=raw.stop_reason or "end_turn",
            usage=usage,
            cost_usd=_anthropic_cost(model, usage, self._pricing_snapshot),
            _raw_content=raw.content,  # preserved for make_assistant_turn
        )

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        # Anthropic requires the original content objects (not our normalized types)
        # so that tool_use block IDs match the tool_result IDs on the next turn.
        return [{"role": "assistant", "content": response._raw_content}]

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        # Anthropic batches all tool results into one user message.
        return [{"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tid, "content": content}
            for tid, content in results
        ]}]
