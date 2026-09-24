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
    openai_style_tokens,
    unavailable_result,
)
from app.runtime.accounting.normalizers.sse import SSEParser

_FAMILY = ProviderFamily.OPENAI_CHAT


def _tokens_from_usage(usage: Mapping[str, Any]) -> TokenBreakdown:
    return openai_style_tokens(
        usage,
        input_field="prompt_tokens",
        output_field="completion_tokens",
        input_details_field="prompt_tokens_details",
        output_details_field="completion_tokens_details",
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
        if not isinstance(usage, dict) or not usage:
            return _unavailable()
        tokens = _tokens_from_usage(usage)
        # #2209 Session 6J reviewer #7 (#2221 review at bbcb5388):
        # {"usage": {}} or a usage dict where every numeric field is
        # absent must return UNAVAILABLE, not COMPLETE. Session 6F
        # applied the same fix to the Anthropic normalizer; this closes
        # the gap for OpenAI Chat.
        if (
            tokens.total_input_tokens is None
            and tokens.total_output_tokens is None
            and tokens.cache_read_tokens is None
        ):
            return _unavailable()
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
                return unavailable_result(_FAMILY, reason="include_usage_not_set")
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
    return unavailable_result(_FAMILY)
