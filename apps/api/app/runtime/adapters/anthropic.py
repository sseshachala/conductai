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

from typing import Any, Callable

from app.runtime.llm_client import (
    GuardProxyBlocked, LLMResponse, LLMTextBlock, LLMToolUseBlock, LLMUsage,
    LLMUpstreamError, _extract_upstream_ids, _should_retry, make_retry_info,
    raise_if_guard_proxy_blocked,
)
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
        # Disable SDK's internal retries — we manage a single authoritative
        # retry layer in create() below. Two layers stacked would result in
        # 3 * 3 = 9 silent attempts on transient failures.
        kwargs: dict[str, Any] = {"api_key": api_key, "max_retries": 0}
        if base_url is not None:
            kwargs["base_url"] = base_url
        if default_headers:
            kwargs["default_headers"] = default_headers
        self._client = _anthropic.Anthropic(**kwargs)
        self._pricing_snapshot = pricing_snapshot
        self._provider = "anthropic"

    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        cache_system: bool = False,
        idempotency_key: str | None = None,
        on_retry: Callable[[dict[str, Any]], None] | None = None,
        outer_attempt: int = 1,
    ) -> LLMResponse:
        import anthropic as _anthropic
        import random as _random
        import time as _time

        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        extra_headers: dict[str, str] = {}
        if cache_system:
            kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
            extra_headers["anthropic-beta"] = "prompt-caching-2024-07-31"
        else:
            kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        # Forward Idempotency-Key via extra_headers. Anthropic's GA support
        # for this header is not documented, but sending an unknown header is
        # safe (ignored) and provides deduplication protection if/when they
        # honor it. Caller supplies a stable key across our retry attempts.
        if idempotency_key:
            extra_headers["Idempotency-Key"] = idempotency_key

        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        # Single retry loop for CF/Render/WAF-intercepted responses. Anthropic's
        # SDK converts HTTP errors to typed exceptions; we inspect the underlying
        # response body/status to decide retry.
        # outer_attempt > 1 → this call is already under an outer retry (e.g.,
        # a future dag_runner block-level retry). Cap internal attempts at 1
        # so 3×3=9 stacked attempts never happen.
        max_attempts = 1 if outer_attempt > 1 else 3
        raw = None
        for attempt in range(max_attempts):
            try:
                raw = self._client.messages.create(**kwargs)
                break
            except _anthropic.APIStatusError as exc:
                # SDK maps HTTP responses to typed exceptions. Real 4xx errors
                # (auth, bad request) subclass APIStatusError but ALSO
                # AuthenticationError/BadRequestError/etc. Retry only when the
                # response is transport-shaped (retryable status or HTML body).
                status = getattr(exc, "status_code", None) or 0
                response = getattr(exc, "response", None)
                headers = dict(response.headers) if response is not None else {}
                body = ""
                if response is not None:
                    try:
                        body = response.text or ""
                    except Exception:
                        body = ""
                content_type = headers.get("content-type", "")

                # Conduct proxy structured policy/config block? Raise typed
                # exception before the generic "surface as-is" path so
                # dag_runner routes it through the Guard UX.
                if response is not None:
                    raise_if_guard_proxy_blocked(provider=self._provider, response=response)

                if not _should_retry(status, content_type, body):
                    raise  # real provider error (auth, invalid request) — surface as-is
                if attempt == max_attempts - 1:
                    cf_ray, request_id = _extract_upstream_ids(headers, body)
                    raise LLMUpstreamError(
                        provider=self._provider,
                        status=status,
                        content_type=content_type,
                        body_snippet=body,
                        cf_ray=cf_ray,
                        request_id=request_id,
                        attempts=attempt + 1,
                    ) from exc
                if on_retry:
                    cf_ray, request_id = _extract_upstream_ids(headers, body)
                    on_retry(make_retry_info(
                        provider=self._provider, status=status,
                        content_type=content_type, attempt=attempt + 1,
                        max_attempts=max_attempts, cf_ray=cf_ray,
                        request_id=request_id,
                    ))
                retry_after = headers.get("retry-after")
                try:
                    sleep_sec = float(retry_after) if retry_after else (0.25 * (4 ** attempt))
                except ValueError:
                    sleep_sec = 0.25 * (4 ** attempt)
                sleep_sec += _random.random() * 0.2
                _time.sleep(min(sleep_sec, 10))
            except (_anthropic.APIConnectionError, _anthropic.APITimeoutError) as exc:
                if attempt == max_attempts - 1:
                    raise LLMUpstreamError(
                        provider=self._provider,
                        status=0,
                        content_type="",
                        body_snippet=f"network error: {exc!s:.200}",
                        cf_ray=None,
                        request_id=None,
                        attempts=attempt + 1,
                    ) from exc
                if on_retry:
                    on_retry(make_retry_info(
                        provider=self._provider, status=0, content_type="",
                        attempt=attempt + 1, max_attempts=max_attempts,
                    ))
                _time.sleep(min(0.25 * (4 ** attempt) + _random.random() * 0.2, 10))

        if raw is None:
            raise RuntimeError("anthropic.create: retry loop exhausted without response or exception")

        # Guard against silent-failure envelopes. A well-formed Anthropic
        # response has content as a non-null list AND at least one of
        # {stop_reason, usage.output_tokens}. If content is None AND we also
        # have no stop_reason and zero tokens, the proxy almost certainly
        # returned an unparseable body that collapsed to {} — silently
        # treating that as "empty response" masks real upstream failures
        # (bad key, malformed stream, upstream 500 with 200 status, etc).
        _stop_reason = getattr(raw, "stop_reason", None)
        _usage = getattr(raw, "usage", None)
        _out_tokens = getattr(_usage, "output_tokens", 0) if _usage else 0
        _content_missing = (raw.content is None) or (isinstance(raw.content, list) and len(raw.content) == 0)

        if _content_missing and not _stop_reason and not _out_tokens:
            try:
                _raw_dict = raw.model_dump() if hasattr(raw, "model_dump") else raw.__dict__
                _diag = {k: v for k, v in _raw_dict.items() if k not in ("content",)}
            except Exception:
                _diag = {"model_dump_failed": True}
            import structlog as _sl
            _sl.get_logger().warning(
                "anthropic.empty_response_envelope",
                model=model, diag=_diag,
            )
            # dag_runner classifies GuardProxyBlocked(error_type="conduct_guard_proxy")
            # as PROXY_CONFIG_ERROR and shows the actionable next-step:
            # "Check Settings → Modules → Guard proxy config and BYO LLM keys."
            raise GuardProxyBlocked(
                provider=self._provider,
                status=200,
                error_type="conduct_guard_proxy",
                message=(
                    f"Upstream returned an empty response envelope for model '{model}'. "
                    "This usually means the workspace has no upstream API key for this provider — "
                    f"add {self._provider.upper()}_API_KEY under Settings → Environments, or set a "
                    "BYO gateway key under Settings → Proxy."
                ),
            )

        # Legitimate empty content with a stop_reason (safety refusal with no
        # text, tool-only replies before message end, etc.) still passes
        # through as an empty response — brain block turn loop handles it.
        _raw_content = raw.content or []

        content: list[LLMTextBlock | LLMToolUseBlock] = []
        for block in _raw_content:
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
            _raw_content=_raw_content,  # preserved for make_assistant_turn
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
