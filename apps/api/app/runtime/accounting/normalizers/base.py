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
