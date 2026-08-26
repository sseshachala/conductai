"""
OpenAI LLMClient adapter.

Handles:
- Tool use normalization (tool_calls -> LLMToolUseBlock)
- stop_reason normalization (stop/tool_calls/length -> end_turn/tool_use/max_tokens)
- Per-model cost computation from pricing table
- Conversation history formatting for assistant/tool turns
"""
from __future__ import annotations

import json
from typing import Any

from typing import Callable

from app.runtime.llm_client import (
    LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage,
    post_with_retry, raise_if_guard_proxy_blocked,
)
from app.runtime.pricing import get_model_rates


def _openai_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("openai", model, pricing_snapshot)
    return round((
        usage.input_tokens    * rates["input"]
        + usage.output_tokens * rates["output"]
    ) / 1_000_000, 6)


class OpenAIClient:
    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None, base_url: str | None = None, default_headers: dict | None = None) -> None:
        self._api_key = api_key
        self._default_headers = default_headers or {}
        self._pricing_snapshot = pricing_snapshot
        self._base_url = base_url
        # Subclasses (e.g. TogetherClient) may override to identify themselves
        # in retry/upstream events without duplicating the whole adapter.
        self._provider = "openai"

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        max_tokens: int = 4096,
        cache_system: bool = False,
        idempotency_key: str | None = None,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
        outer_attempt: int = 1,
    ) -> LLMResponse:
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

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._default_headers,
        }
        # OpenAI documents Idempotency-Key as GA — safe to include when caller
        # supplies a stable key. Retries below reuse the same key so OpenAI
        # deduplicates a request that was intercepted mid-flight.
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        # Cap internal retries at 1 when called under an outer retry (e.g. a
        # future dag_runner block-level retry) to avoid 3×3 = 9 silent attempts.
        _max_attempts = 1 if outer_attempt > 1 else 3
        r = post_with_retry(
            url=f"{self._base_url or 'https://api.openai.com'}/v1/chat/completions",
            headers=headers,
            json_body=payload,
            provider=self._provider,
            max_attempts=_max_attempts,
            on_retry=on_retry,
        )
        # Conduct proxy structured policy/config blocks: turn JSON error into
        # a typed exception dag_runner classifies through the Guard UX path.
        raise_if_guard_proxy_blocked(provider=self._provider, response=r)
        if r.status_code >= 400:
            raise Exception(f"OpenAI {r.status_code}: {r.text[:500]}")
        raw = r.json()

        choice = ((raw.get("choices") or [{}])[0])
        message = choice.get("message") or {}
        finish_reason = choice.get("finish_reason") or "stop"

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        text = message.get("content") or message.get("reasoning_content") or ""
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


    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Streaming not yet implemented for openai. TODO: backfill when needed."""
        raise NotImplementedError(
            "stream() not implemented for openai adapter yet — currently only AnthropicClient. "
            "File an issue if you need this."
        )
        yield  # unreachable — makes function a generator for type-checkers

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
