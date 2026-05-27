"""
LLM client abstraction — provider-agnostic interface for Brain block LLM calls.

Each adapter implements three methods:
  create()                — issue one call, return normalized LLMResponse (with cost_usd)
  make_assistant_turn()   — format the assistant's response for conversation history
  make_tool_results_turn()— format tool results for conversation history

Message format differs by provider:
  Anthropic: tool results → single {"role": "user", "content": [tool_result, ...]}
  OpenAI:    tool results → one {"role": "tool", ...} message per result

Both make_* methods return list[dict] so the executor always does messages.extend(...).

Adding a new provider: implement LLMClient, pass to _execute_brain via the llm kwarg.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ── Normalized response types ─────────────────────────────────────────────────

@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0    # prompt-cache read hits (Anthropic only; 0 for others)
    cache_write_tokens: int = 0   # prompt-cache write cost (Anthropic only; 0 for others)


@dataclass
class LLMTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class LLMToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: list[LLMTextBlock | LLMToolUseBlock]
    stop_reason: str        # normalized: "end_turn" | "tool_use" | "max_tokens"
    usage: LLMUsage
    cost_usd: float = 0.0  # computed by adapter from usage + model pricing; executor sums across turns
    _raw_content: Any = field(default=None, repr=False)  # provider-native content; used by make_assistant_turn


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
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
        """
        Issue one LLM call and return a normalized LLMResponse.

        Args:
            model:        Model ID string (as returned by model_router.resolve)
            messages:     Conversation history — [{"role": "user"|"assistant", "content": ...}]
            system:       System prompt as a plain string; adapter handles caching internally
            tools:        Tool definitions in BRAIN_TOOLS format (name/description/input_schema).
                          None for single-shot (non-agentic) calls.
            max_tokens:   Max tokens for this response
            cache_system: When True, adapter wraps system prompt with cache_control so
                          turns 2-N in an agentic loop read from cache (~10% cost)
        """
        ...

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        """
        Return the message(s) representing the assistant's turn, ready to extend messages[].

        Anthropic: [{"role": "assistant", "content": <raw content blocks>}]
        OpenAI:    [{"role": "assistant", "content": text, "tool_calls": [...]}]
        """
        ...

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        """
        Return the message(s) that deliver tool results back to the model.

        Args:
            results: list of (tool_use_id, result_content_str)

        Anthropic: [{"role": "user", "content": [{"type": "tool_result", ...}, ...]}]  — one batched message
        OpenAI:    [{"role": "tool", "tool_call_id": id, "content": result}, ...]      — one message per result
        """
        ...


# ── Anthropic adapter ─────────────────────────────────────────────────────────

# Per-model pricing in USD per 1M tokens.
# Cache read ≈ 10% of input price; cache write ≈ 125% of input price.
_ANTHROPIC_PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {
        "input":       3.00,
        "output":     15.00,
        "cache_read":  0.30,
        "cache_write": 3.75,
    },
    "claude-opus-4-7": {
        "input":       15.00,
        "output":      75.00,
        "cache_read":   1.50,
        "cache_write": 18.75,
    },
    "claude-haiku-4-5-20251001": {
        "input":       0.80,
        "output":      4.00,
        "cache_read":  0.08,
        "cache_write": 1.00,
    },
}

# Fallback: Sonnet rates for any unrecognized model ID
_ANTHROPIC_PRICING_DEFAULT = _ANTHROPIC_PRICING["claude-sonnet-4-6"]


def _anthropic_cost(model: str, usage: LLMUsage) -> float:
    rates = _ANTHROPIC_PRICING.get(model, _ANTHROPIC_PRICING_DEFAULT)
    return round((
        usage.input_tokens         * rates["input"]
        + usage.output_tokens      * rates["output"]
        + usage.cache_read_tokens  * rates["cache_read"]
        + usage.cache_write_tokens * rates["cache_write"]
    ) / 1_000_000, 6)


class AnthropicClient:
    """
    LLMClient adapter for Anthropic.

    Handles:
    - Prompt caching via cache_system flag (ephemeral cache_control on system block)
    - Tool use normalization (Anthropic tool_use content blocks → LLMToolUseBlock)
    - stop_reason passthrough (Anthropic already uses "end_turn" / "tool_use" / "max_tokens")
    - Per-model cost computation from pricing table
    - Conversation history formatting (Anthropic requires raw content objects for assistant turns)
    """

    def __init__(self, api_key: str) -> None:
        import anthropic as _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)

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
            cost_usd=_anthropic_cost(model, usage),
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
