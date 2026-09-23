"""OpenAI Chat Completions usage normalizer.

Streaming quirks:

- Usage is emitted ONLY when the caller sets ``stream_options.include_usage``.
  Without that flag, streams never carry usage — we return UNAVAILABLE.
- Cached-input is reported at ``usage.prompt_tokens_details.cached_tokens``
  and is a SUBSET of ``prompt_tokens`` (not an additional bucket).
- Reasoning tokens (o-series) live at
  ``usage.completion_tokens_details.reasoning_tokens`` and are a SUBSET of
  ``completion_tokens`` — invariant #5, no double charge.
- ``[DONE]`` sentinel appears after the final chunk.

OpenAI-compatible providers (Qwen, Groq, DeepSeek, Together, Fireworks, ...)
speak this shape. Any cache/reasoning field they omit → we report None for
those fields, not zero (invariant #4).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

from app.runtime.accounting.contracts import (
    TokenBreakdown,
    UsageCompleteness,
    UsageOrigin,
)
from app.runtime.accounting.normalizers.base import (
    NORMALIZER_VERSION,
    NormalizedUsage,
    ProviderFamily,
)
from app.runtime.accounting.normalizers.sse import SSEParser

_FAMILY = ProviderFamily.OPENAI_CHAT


def _tokens_from_usage(usage: Mapping[str, Any]) -> TokenBreakdown:
    prompt = usage.get("prompt_tokens")
    completion = usage.get("completion_tokens")

    prompt_details = usage.get("prompt_tokens_details") or {}
    cached = prompt_details.get("cached_tokens") if isinstance(prompt_details, dict) else None

    completion_details = usage.get("completion_tokens_details") or {}
    reasoning = (
        completion_details.get("reasoning_tokens")
        if isinstance(completion_details, dict)
        else None
    )

    prompt_int = int(prompt) if isinstance(prompt, (int, float)) else None
    cached_int = int(cached) if isinstance(cached, (int, float)) else None
    uncached = None
    if prompt_int is not None and cached_int is not None:
        uncached = max(0, prompt_int - cached_int)
    elif prompt_int is not None:
        uncached = prompt_int

    return TokenBreakdown(
        total_input_tokens=prompt_int,
        total_output_tokens=int(completion) if isinstance(completion, (int, float)) else None,
        uncached_input_tokens=uncached,
        cache_read_tokens=cached_int,
        cache_write_tokens_by_tier={},  # Chat Completions has no cache-write tier
        reasoning_output_tokens=int(reasoning) if isinstance(reasoning, (int, float)) else None,
    )


class OpenAIChatNormalizer:
    family = _FAMILY
    version = NORMALIZER_VERSION

    def normalize_json(self, payload: bytes | str | dict) -> NormalizedUsage:
        obj: Any
        if isinstance(payload, (bytes, str)):
            try:
                obj = json.loads(payload)
            except (ValueError, TypeError):
                return _unavailable()
        else:
            obj = payload
        if not isinstance(obj, dict):
            return _unavailable()
        usage = obj.get("usage")
        if not isinstance(usage, dict):
            return _unavailable()
        tokens = _tokens_from_usage(usage)
        return NormalizedUsage(
            tokens=tokens,
            origin=UsageOrigin.PROVIDER_REPORTED,
            completeness=UsageCompleteness.COMPLETE,
            provider_family=_FAMILY,
            raw_usage=dict(usage),
        )

    def normalize_sse(self, payload: bytes) -> NormalizedUsage:
        parser = SSEParser()
        last_usage: dict[str, Any] = {}
        saw_done = False
        saw_any_chunk = False

        def _handle(data: str) -> None:
            nonlocal last_usage, saw_done, saw_any_chunk
            data = data.strip()
            if data == "[DONE]":
                saw_done = True
                return
            saw_any_chunk = True
            try:
                obj = json.loads(data)
            except ValueError:
                return
            if not isinstance(obj, dict):
                return
            usage = obj.get("usage")
            if isinstance(usage, dict):
                # Chat streams emit usage only in a terminal chunk when
                # stream_options.include_usage=true. Overwrite (not merge) —
                # OpenAI documents cumulative totals in that chunk.
                last_usage = dict(usage)

        for evt in parser.feed(payload):
            _handle(evt.data)
        for evt in parser.flush():
            _handle(evt.data)

        if not last_usage:
            # Stream had chunks but no usage payload: caller did not opt in,
            # or provider does not support include_usage. Distinguishable
            # from a truly interrupted stream (which would have neither).
            if saw_any_chunk:
                return NormalizedUsage(
                    tokens=TokenBreakdown(),
                    origin=UsageOrigin.MISSING,
                    completeness=UsageCompleteness.UNAVAILABLE,
                    provider_family=_FAMILY,
                    raw_usage={"reason": "include_usage_not_set"},
                )
            return _unavailable()

        tokens = _tokens_from_usage(last_usage)
        completeness = UsageCompleteness.COMPLETE if saw_done else UsageCompleteness.PARTIAL
        return NormalizedUsage(
            tokens=tokens,
            origin=UsageOrigin.NORMALIZED_STREAM,
            completeness=completeness,
            provider_family=_FAMILY,
            raw_usage=last_usage,
        )


def _unavailable() -> NormalizedUsage:
    return NormalizedUsage(
        tokens=TokenBreakdown(),
        origin=UsageOrigin.MISSING,
        completeness=UsageCompleteness.UNAVAILABLE,
        provider_family=_FAMILY,
        raw_usage={},
    )
