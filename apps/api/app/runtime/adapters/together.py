"""
Together AI LLMClient adapter.

Together AI is OpenAI-compatible — thin wrapper that sets the correct base URL
and Together-specific pricing. Supports all Llama, Mixtral, Qwen, and other
open models hosted on Together's inference platform.
"""
from __future__ import annotations

from typing import Any

from app.runtime.adapters.openai import OpenAIClient
from app.runtime.llm_client import LLMResponse, LLMUsage

_TOGETHER_BASE = "https://api.together.xyz/v1"

# Pricing per 1M tokens (USD) — https://www.together.ai/pricing
# Add models as needed; unknown models fall back to zero cost.
_TOGETHER_PRICING: dict[str, dict[str, float]] = {
    # Llama 3.x
    "meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo":  {"input": 0.18,  "output": 0.18},
    "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo": {"input": 0.88,  "output": 0.88},
    "meta-llama/Meta-Llama-3.3-70B-Instruct-Turbo": {"input": 0.88,  "output": 0.88},
    # Qwen 2.5
    "Qwen/Qwen2.5-7B-Instruct-Turbo":               {"input": 0.20,  "output": 0.20},
    "Qwen/Qwen2.5-72B-Instruct-Turbo":              {"input": 1.20,  "output": 1.20},
    # Qwen 3.5
    "Qwen/Qwen3.5-9B":                              {"input": 0.20,  "output": 0.20},
    # Mixtral
    "mistralai/Mixtral-8x7B-Instruct-v0.1":         {"input": 0.60,  "output": 0.60},
    "mistralai/Mixtral-8x22B-Instruct-v0.1":        {"input": 1.20,  "output": 1.20},
    # DeepSeek
    "deepseek-ai/DeepSeek-R1":                       {"input": 3.00,  "output": 7.00},
    "deepseek-ai/DeepSeek-V3":                       {"input": 1.25,  "output": 1.25},
}


def _together_cost(model: str, usage: LLMUsage) -> float:
    rates = _TOGETHER_PRICING.get(model, {"input": 0.0, "output": 0.0})
    return round(
        (usage.input_tokens * rates["input"] + usage.output_tokens * rates["output"]) / 1_000_000,
        6,
    )


class TogetherClient(OpenAIClient):
    """Together AI adapter — inherits all OpenAI-compatible logic, overrides URL + cost."""

    def __init__(self, api_key: str, pricing_snapshot: Any = None, base_url: str | None = None) -> None:
        super().__init__(
            api_key=api_key,
            pricing_snapshot=pricing_snapshot,
            base_url=base_url or _TOGETHER_BASE,
        )

    def create(self, *, model: str, messages: list[dict], system: str, **kwargs) -> LLMResponse:
        resp = super().create(model=model, messages=messages, system=system, **kwargs)
        # Override cost with Together-specific pricing
        resp.cost_usd = _together_cost(model, resp.usage)
        return resp
