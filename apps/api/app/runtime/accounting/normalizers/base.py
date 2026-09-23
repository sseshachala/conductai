"""Shared types for the family normalizers."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.runtime.accounting.contracts import (
    TokenBreakdown,
    UsageCompleteness,
    UsageOrigin,
)

NORMALIZER_VERSION = "v1"


class ProviderFamily(str, Enum):
    """The protocol family a provider speaks.

    Provider identity is separate from family — Bedrock-Claude speaks
    Anthropic Messages; Groq speaks OpenAI Chat. Family drives parsing;
    provider drives pricing.
    """

    ANTHROPIC_MESSAGES = "anthropic_messages"
    OPENAI_CHAT = "openai_chat"
    OPENAI_RESPONSES = "openai_responses"
    LITELLM = "litellm"


@dataclass(frozen=True)
class NormalizedUsage:
    """One provider response normalized to the shared TokenBreakdown."""

    tokens: TokenBreakdown
    origin: UsageOrigin
    completeness: UsageCompleteness
    provider_family: ProviderFamily
    normalizer_version: str = NORMALIZER_VERSION
    raw_usage: Mapping[str, Any] = field(default_factory=dict)


def unavailable_result(
    family: ProviderFamily,
    *,
    reason: str | None = None,
) -> NormalizedUsage:
    """No usage payload was extractable. Shared by every family normalizer.

    ``reason`` (optional) is stored in raw_usage so callers can distinguish
    a truly missing payload from a caller misconfiguration (e.g. OpenAI Chat
    stream without ``stream_options.include_usage``).
    """
    return NormalizedUsage(
        tokens=TokenBreakdown(),
        origin=UsageOrigin.MISSING,
        completeness=UsageCompleteness.UNAVAILABLE,
        provider_family=family,
        raw_usage={"reason": reason} if reason else {},
    )


def openai_style_tokens(
    usage: Mapping[str, Any],
    *,
    input_field: str,
    output_field: str,
    input_details_field: str,
    output_details_field: str,
) -> TokenBreakdown:
    """Shared token extraction for OpenAI-shape families.

    Chat Completions and Responses share the same schema *shape* under
    different field names: total input, total output, ``*_tokens_details``
    dicts for cached_tokens (subset of input) and reasoning_tokens (subset
    of output — invariant #5). Anthropic Messages does NOT fit this shape
    because its cache_read is a separate bucket, not a subset of input.
    """
    total_input = usage.get(input_field)
    total_output = usage.get(output_field)

    input_details = usage.get(input_details_field) or {}
    cached = input_details.get("cached_tokens") if isinstance(input_details, dict) else None

    output_details = usage.get(output_details_field) or {}
    reasoning = (
        output_details.get("reasoning_tokens") if isinstance(output_details, dict) else None
    )

    input_int = int(total_input) if isinstance(total_input, (int, float)) else None
    cached_int = int(cached) if isinstance(cached, (int, float)) else None
    uncached = None
    if input_int is not None and cached_int is not None:
        uncached = max(0, input_int - cached_int)
    elif input_int is not None:
        uncached = input_int

    return TokenBreakdown(
        total_input_tokens=input_int,
        total_output_tokens=int(total_output) if isinstance(total_output, (int, float)) else None,
        uncached_input_tokens=uncached,
        cache_read_tokens=cached_int,
        cache_write_tokens_by_tier={},
        reasoning_output_tokens=int(reasoning) if isinstance(reasoning, (int, float)) else None,
    )
