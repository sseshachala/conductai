"""OpenAI Responses API usage normalizer.

Responses uses a different usage schema than Chat Completions:

- ``usage.input_tokens`` / ``usage.output_tokens`` (not prompt/completion)
- ``usage.input_tokens_details.cached_tokens`` for cached input
- ``usage.output_tokens_details.reasoning_tokens`` for reasoning subset

Streaming: usage arrives in the terminal ``response.completed`` event.
Interrupted before completed → PARTIAL if any partial event carried usage,
UNAVAILABLE otherwise.
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

_FAMILY = ProviderFamily.OPENAI_RESPONSES


def _tokens_from_usage(usage: Mapping[str, Any]) -> TokenBreakdown:
    return openai_style_tokens(
        usage,
        input_field="input_tokens",
        output_field="output_tokens",
        input_details_field="input_tokens_details",
        output_details_field="output_tokens_details",
    )


class OpenAIResponsesNormalizer:
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
        # #2209 Session 6J reviewer #7 (#2221 review at bbcb5388): same
        # empty-usage guard as OpenAI Chat + Anthropic (Session 6F).
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
        final_usage: dict[str, Any] = {}
        saw_completed = False

        def _handle(event_name: str, data: str) -> None:
            nonlocal final_usage, saw_completed
            try:
                obj = json.loads(data)
            except ValueError:
                return
            if not isinstance(obj, dict):
                return
            evt_type = obj.get("type") or event_name
            if evt_type == "response.completed":
                saw_completed = True
                response = obj.get("response") or {}
                usage = response.get("usage") if isinstance(response, dict) else None
                if isinstance(usage, dict):
                    final_usage = dict(usage)
            elif evt_type in ("response.incomplete", "response.failed"):
                response = obj.get("response") or {}
                usage = response.get("usage") if isinstance(response, dict) else None
                if isinstance(usage, dict):
                    final_usage = dict(usage)

        for evt in parser.feed(payload):
            _handle(evt.event, evt.data)
        for evt in parser.flush():
            _handle(evt.event, evt.data)

        if not final_usage:
            return _unavailable()

        completeness = UsageCompleteness.COMPLETE if saw_completed else UsageCompleteness.PARTIAL
        return NormalizedUsage(
            tokens=_tokens_from_usage(final_usage),
            origin=UsageOrigin.NORMALIZED_STREAM,
            completeness=completeness,
            provider_family=_FAMILY,
            raw_usage=final_usage,
        )


def _unavailable() -> NormalizedUsage:
    return unavailable_result(_FAMILY)
