"""
Perplexity LLMClient adapter (OpenAI-compatible endpoint).

Perplexity's Agent API routes through a single key to Sonar, GPT-4o, Claude,
Gemini etc. — same interface as OpenAIClient, different base URL.
Tool use is not supported on Sonar models; use for single-shot summarization
and research tasks only (no agentic loops).
"""
from __future__ import annotations

from typing import Any, Callable, Iterator

from app.runtime.llm_client import (
    LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage,
    post_with_retry, raise_if_guard_proxy_blocked,
)
from app.runtime.pricing import get_model_rates


def _perplexity_cost(model: str, usage: LLMUsage, pricing_snapshot: dict[str, Any] | None = None) -> float:
    rates, _ = get_model_rates("perplexity", model, pricing_snapshot)
    return round((
        usage.input_tokens    * rates["input"]
        + usage.output_tokens * rates["output"]
    ) / 1_000_000, 6)


class PerplexityClient:
    def __init__(self, api_key: str, pricing_snapshot: dict[str, Any] | None = None, base_url: str | None = None, default_headers: dict | None = None) -> None:
        self._api_key = api_key
        self._pricing_snapshot = pricing_snapshot
        self._base_url = base_url
        self._default_headers = default_headers or {}
        self._provider = "perplexity"

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        tool_choice: dict | None = None,
        max_tokens: int = 4096,
        cache_system: bool = True,
        idempotency_key: str | None = None,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
        outer_attempt: int = 1,
    ) -> LLMResponse:
        _ = cache_system  # not supported

        pplx_messages = [{"role": "system", "content": system}, *messages]
        payload: dict[str, Any] = {
            "model": model,
            "messages": pplx_messages,
            "max_tokens": max_tokens,
        }
        # Perplexity Sonar models don't support tool_calls; skip tools silently.

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._default_headers,
        }
        # Perplexity does not document Idempotency-Key GA support, but the API
        # is OpenAI-compatible and safe to send. Header will be ignored if
        # unsupported; protects if they honor it.
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        _max_attempts = 1 if outer_attempt > 1 else 3
        r = post_with_retry(
            url=f"{self._base_url or 'https://api.perplexity.ai'}/chat/completions",
            headers=headers,
            json_body=payload,
            provider=self._provider,
            max_attempts=_max_attempts,
            on_retry=on_retry,
        )
        raise_if_guard_proxy_blocked(provider=self._provider, response=r)
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


    def stream(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        max_tokens: int = 4096,
    ) -> Iterator[str]:
        """Streaming not yet implemented for perplexity. TODO: backfill when needed."""
        raise NotImplementedError(
            "stream() not implemented for perplexity adapter yet — currently only AnthropicClient. "
            "File an issue if you need this."
        )
        yield  # unreachable — makes function a generator for type-checkers

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        msg = response._raw_content or {}
        return [{"role": "assistant", "content": msg.get("content") or ""}]

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        return [
            {"role": "tool", "tool_call_id": tid, "content": content}
            for tid, content in results
        ]
