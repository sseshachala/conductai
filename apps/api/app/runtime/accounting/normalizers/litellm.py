"""LiteLLM-normalized usage.

LiteLLM's Router / SDK normalize provider responses into an OpenAI Chat
Completions-shaped ``usage`` block, extending with per-provider fields via
``prompt_tokens_details`` / ``completion_tokens_details`` where available.

For usage extraction purposes this is byte-identical to
``OpenAIChatNormalizer``; we keep it as a distinct family so callers can
attribute the transport correctly and future divergence (e.g. LiteLLM adding
its own cache tier semantics) has a home.
"""

from __future__ import annotations

from app.runtime.accounting.normalizers.base import (
    NORMALIZER_VERSION,
    NormalizedUsage,
    ProviderFamily,
)
from app.runtime.accounting.normalizers.openai_chat import OpenAIChatNormalizer


class LiteLLMNormalizer:
    family = ProviderFamily.LITELLM
    version = NORMALIZER_VERSION

    def __init__(self) -> None:
        self._inner = OpenAIChatNormalizer()

    def normalize_json(self, payload) -> NormalizedUsage:
        inner = self._inner.normalize_json(payload)
        return NormalizedUsage(
            tokens=inner.tokens,
            origin=inner.origin,
            completeness=inner.completeness,
            provider_family=ProviderFamily.LITELLM,
            normalizer_version=NORMALIZER_VERSION,
            raw_usage=inner.raw_usage,
        )

    def normalize_sse(self, payload) -> NormalizedUsage:
        inner = self._inner.normalize_sse(payload)
        return NormalizedUsage(
            tokens=inner.tokens,
            origin=inner.origin,
            completeness=inner.completeness,
            provider_family=ProviderFamily.LITELLM,
            normalizer_version=NORMALIZER_VERSION,
            raw_usage=inner.raw_usage,
        )
