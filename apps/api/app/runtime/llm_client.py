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

import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.runtime.pricing import get_model_rates


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


def _anthropic_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("anthropic", model, pricing_snapshot)
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

    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None) -> None:
        import anthropic as _anthropic
        self._client = _anthropic.Anthropic(api_key=api_key)
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


def _openai_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("openai", model, pricing_snapshot)
    return round((
        usage.input_tokens * rates["input"]
        + usage.output_tokens * rates["output"]
    ) / 1_000_000, 6)


class OpenAIClient:
    """
    LLMClient adapter for OpenAI Chat Completions.

    Handles:
    - Tool use normalization (tool_calls -> LLMToolUseBlock)
    - stop_reason normalization (stop/tool_calls/length)
    - Per-model cost computation from pricing table
    - Conversation history formatting for assistant/tool turns
    """

    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None) -> None:
        self._api_key = api_key
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
        import httpx

        # OpenAI Chat Completions expects the system prompt as a system message.
        # cache_system is Anthropic-specific; ignored here.
        _ = cache_system

        oai_messages = [{"role": "system", "content": system}, *messages]
        payload: dict[str, Any] = {
            "model": model,
            "messages": oai_messages,
            "max_tokens": max_tokens,
        }

        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "parameters": t.get("input_schema", {"type": "object", "properties": {}}),
                    },
                }
                for t in tools
            ]

        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        raw = r.json()

        choice = ((raw.get("choices") or [{}])[0])
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        text = message.get("content")
        if isinstance(text, str) and text.strip():
            content.append(LLMTextBlock(text=text))

        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            raw_args = fn.get("arguments") or "{}"
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except Exception:
                parsed_args = {}
            content.append(LLMToolUseBlock(
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                input=parsed_args if isinstance(parsed_args, dict) else {},
            ))

        u = raw.get("usage") or {}
        usage = LLMUsage(
            input_tokens=int(u.get("prompt_tokens", 0) or 0),
            output_tokens=int(u.get("completion_tokens", 0) or 0),
            cache_read_tokens=0,
            cache_write_tokens=0,
        )

        stop_reason_map = {
            "tool_calls": "tool_use",
            "length": "max_tokens",
            "stop": "end_turn",
        }
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
            cost_usd=_openai_cost(model, usage, self._pricing_snapshot),
            _raw_content=message,
        )

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        # OpenAI expects assistant text and tool_calls on the assistant message.
        msg = response._raw_content or {}
        out: dict[str, Any] = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            out["tool_calls"] = msg["tool_calls"]
        return [out]

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        # OpenAI sends one role=tool message per tool result.
        return [
            {"role": "tool", "tool_call_id": tid, "content": content}
            for tid, content in results
        ]


def _perplexity_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("perplexity", model, pricing_snapshot)
    return round((
        usage.input_tokens * rates["input"]
        + usage.output_tokens * rates["output"]
    ) / 1_000_000, 6)


class PerplexityClient:
    """
    LLMClient adapter for Perplexity AI (OpenAI-compatible endpoint).

    Perplexity's Agent API routes through a single key to Sonar, GPT-4o, Claude,
    Gemini etc. — same interface as OpenAIClient, different base URL.
    Tool use is not supported on Sonar models; use for single-shot summarization
    and research tasks only (no agentic loops).
    """

    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None) -> None:
        self._api_key = api_key
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
        import httpx

        _ = cache_system  # not supported

        pplx_messages = [{"role": "system", "content": system}, *messages]
        payload: dict[str, Any] = {
            "model": model,
            "messages": pplx_messages,
            "max_tokens": max_tokens,
        }
        # Perplexity Sonar models don't support tool_calls; skip tools silently.

        r = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        r.raise_for_status()
        raw = r.json()

        choice = ((raw.get("choices") or [{}])[0])
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        text = message.get("content")
        if isinstance(text, str) and text.strip():
            content.append(LLMTextBlock(text=text))

        u = raw.get("usage") or {}
        usage = LLMUsage(
            input_tokens=int(u.get("prompt_tokens", 0) or 0),
            output_tokens=int(u.get("completion_tokens", 0) or 0),
        )

        stop_reason_map = {"length": "max_tokens", "stop": "end_turn"}
        stop_reason = stop_reason_map.get(finish_reason, "end_turn")

        return LLMResponse(
            content=content,
            stop_reason=stop_reason,
            usage=usage,
            cost_usd=_perplexity_cost(model, usage, self._pricing_snapshot),
            _raw_content=message,
        )

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        msg = response._raw_content or {}
        return [{"role": "assistant", "content": msg.get("content") or ""}]

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        return [
            {"role": "tool", "tool_call_id": tid, "content": content}
            for tid, content in results
        ]
