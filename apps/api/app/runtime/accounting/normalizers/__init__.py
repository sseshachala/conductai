"""Protocol-family normalizers for provider usage payloads (#2209 Session 3).

Each family emits its own shape (Anthropic Messages, OpenAI Chat Completions,
OpenAI Responses, LiteLLM-normalized). This module parses each into the
shared ``TokenBreakdown`` + provenance fields defined in Session 1 contracts.

Provider quirks are NOT hidden — an OpenAI-compatible provider that speaks
Chat Completions still needs a fixture + rate validation per Sudhi's
correction #2 (protocol compatibility ≠ accounting compatibility).

Wiring into callers lands in Session 4 behind shadow.
"""

from app.runtime.accounting.normalizers.anthropic_messages import (
    AnthropicMessagesNormalizer,
)
from app.runtime.accounting.normalizers.base import (
    NORMALIZER_VERSION,
    NormalizedUsage,
    ProviderFamily,
)
from app.runtime.accounting.normalizers.litellm import LiteLLMNormalizer
from app.runtime.accounting.normalizers.openai_chat import OpenAIChatNormalizer
from app.runtime.accounting.normalizers.openai_responses import OpenAIResponsesNormalizer
from app.runtime.accounting.normalizers.sse import SSEEvent, SSEParser

_REGISTRY = {
    ProviderFamily.ANTHROPIC_MESSAGES: AnthropicMessagesNormalizer(),
    ProviderFamily.OPENAI_CHAT: OpenAIChatNormalizer(),
    ProviderFamily.OPENAI_RESPONSES: OpenAIResponsesNormalizer(),
    ProviderFamily.LITELLM: LiteLLMNormalizer(),
}


def normalize_json(family: ProviderFamily, payload) -> NormalizedUsage:
    """Parse a complete JSON response into a NormalizedUsage."""
    return _REGISTRY[family].normalize_json(payload)


def normalize_sse(family: ProviderFamily, payload) -> NormalizedUsage:
    """Parse a full SSE byte stream into a NormalizedUsage.

    For chunk-by-chunk parsing, use ``get_normalizer(family)`` and feed the
    stateful SSEParser directly.
    """
    return _REGISTRY[family].normalize_sse(payload)


def get_normalizer(family: ProviderFamily):
    """Return the normalizer instance for one family."""
    return _REGISTRY[family]


__all__ = [
    "NORMALIZER_VERSION",
    "AnthropicMessagesNormalizer",
    "LiteLLMNormalizer",
    "NormalizedUsage",
    "OpenAIChatNormalizer",
    "OpenAIResponsesNormalizer",
    "ProviderFamily",
    "SSEEvent",
    "SSEParser",
    "get_normalizer",
    "normalize_json",
    "normalize_sse",
]
