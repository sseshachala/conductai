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
)
from app.runtime.accounting.normalizers.sse import SSEParser

_FAMILY = ProviderFamily.OPENAI_RESPONSES


def _tokens_from_usage(usage: Mapping[str, Any]) -> TokenBreakdown:
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")

    input_details = usage.get("input_tokens_details") or {}
    cached = input_details.get("cached_tokens") if isinstance(input_details, dict) else None

    output_details = usage.get("output_tokens_details") or {}
    reasoning = (
        output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
    )

    input_int = int(input_tokens) if isinstance(input_tokens, (int, float)) else None
    cached_int = int(cached) if isinstance(cached, (int, float)) else None
    uncached = None
    if input_int is not None and cached_int is not None:
        uncached = max(0, input_int - cached_int)
    elif input_int is not None:
        uncached = input_int

    return TokenBreakdown(
        total_input_tokens=input_int,
        total_output_tokens=int(output_tokens) if isinstance(output_tokens, (int, float)) else None,
        uncached_input_tokens=uncached,
        cache_read_tokens=cached_int,
        cache_write_tokens_by_tier={},
        reasoning_output_tokens=int(reasoning) if isinstance(reasoning, (int, float)) else None,
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
        if not isinstance(usage, dict):
            return _unavailable()
        return NormalizedUsage(
            tokens=_tokens_from_usage(usage),
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
    return NormalizedUsage(
        tokens=TokenBreakdown(),
        origin=UsageOrigin.MISSING,
        completeness=UsageCompleteness.UNAVAILABLE,
        provider_family=_FAMILY,
        raw_usage={},
    )
