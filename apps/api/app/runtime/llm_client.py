"""
LLM client abstraction — provider-agnostic interface for Brain block LLM calls.

Each adapter implements three methods:
  create()                — issue one call, return normalized LLMResponse (with cost_usd)
  make_assistant_turn()   — format the assistant's response for conversation history
  make_tool_results_turn()— format tool results for conversation history

Message format differs by provider:
  Anthropic: tool results -> single {"role": "user", "content": [tool_result, ...]}
  OpenAI:    tool results -> one {"role": "tool", ...} message per result

Both make_* methods return list[dict] so the executor always does messages.extend(...).

Adding a new provider: implement LLMClient, add to adapters/, register in client_for().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


# ── Normalized response types ─────────────────────────────────────────────────

@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0    # prompt-cache read hits (Anthropic only; 0 for others)
    cache_write_tokens: int = 0   # prompt-cache write cost (Anthropic only; 0 for others)


@dataclass
class LLMTextBlock:
    type: str = "text"
    text: str = ""


@dataclass
class LLMToolUseBlock:
    type: str = "tool_use"
    id: str = ""
    name: str = ""
    input: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: list[LLMTextBlock | LLMToolUseBlock]
    stop_reason: str        # normalized: "end_turn" | "tool_use" | "max_tokens"
    usage: LLMUsage
    cost_usd: float = 0.0  # computed by adapter from usage + model pricing; executor sums across turns
    _raw_content: Any = field(default=None, repr=False)  # provider-native content; used by make_assistant_turn

    def to_cache_dict(self) -> dict:
        def _block_to_dict(b: Any) -> dict:
            if hasattr(b, "model_dump"):
                return b.model_dump()
            if isinstance(b, (LLMTextBlock, LLMToolUseBlock)):
                return b.__dict__
            return b if isinstance(b, dict) else {}

        raw = [_block_to_dict(b) for b in self._raw_content] if self._raw_content else None
        return {
            "content": [c.__dict__ for c in self.content],
            "stop_reason": self.stop_reason,
            "usage": self.usage.__dict__,
            "cost_usd": self.cost_usd,
            "_raw_content": raw,
        }

    @classmethod
    def from_cache_dict(cls, d: dict) -> "LLMResponse":
        usage = LLMUsage(**d["usage"])
        content = [
            LLMToolUseBlock(**b) if b.get("type") == "tool_use" else LLMTextBlock(**b)
            for b in d["content"]
        ]
        return cls(
            content=content,
            stop_reason=d["stop_reason"],
            usage=usage,
            cost_usd=d.get("cost_usd", 0.0),
            _raw_content=d.get("_raw_content"),  # plain dicts — accepted by Anthropic/OpenAI APIs
        )


# ── Protocol ──────────────────────────────────────────────────────────────────

@runtime_checkable
class LLMClient(Protocol):
    def create(
        self,
        *,
        model: str,
        messages: list[dict],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
        cache_system: bool = False,
    ) -> LLMResponse:
        """
        Issue one LLM call and return a normalized LLMResponse.

        Args:
            model:        Model ID string (as returned by model_router.resolve)
            messages:     Conversation history — [{"role": "user"|"assistant", "content": ...}]
            system:       System prompt as a plain string; adapter handles caching internally
            tools:        Tool definitions in BRAIN_TOOLS format (name/description/input_schema).
                          None for single-shot (non-agentic) calls.
            max_tokens:   Max tokens for this response
            cache_system: When True, adapter wraps system prompt with cache_control so
                          turns 2-N in an agentic loop read from cache (~10% cost)
        """
        ...

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        """
        Return the message(s) representing the assistant's turn, ready to extend messages[].

        Anthropic: [{"role": "assistant", "content": <raw content blocks>}]
        OpenAI:    [{"role": "assistant", "content": text, "tool_calls": [...]}]
        """
        ...

    def make_tool_results_turn(self, results: list[tuple[str, str]]) -> list[dict]:
        """
        Return the message(s) that deliver tool results back to the model.

        Args:
            results: list of (tool_use_id, result_content_str)

        Anthropic: [{"role": "user", "content": [{"type": "tool_result", ...}, ...]}]  — one batched message
        OpenAI:    [{"role": "tool", "tool_call_id": id, "content": result}, ...]      — one message per result
        """
        ...


# ── Factory ───────────────────────────────────────────────────────────────────

def client_for(provider: str, api_key: str, pricing_snapshot: dict[str, Any] | None = None, base_url: str | None = None) -> LLMClient:
    """
    Return the correct adapter instance for the given provider slug.

    Args:
        provider:          One of "anthropic", "openai", "perplexity"
        api_key:           Provider API key (decrypted at point of use — never stored)
        pricing_snapshot:  Optional frozen pricing dict from freeze_pricing_snapshot()
        base_url:          Optional override (e.g. Guard proxy URL)

    Raises:
        ValueError: if provider is unrecognised
    """
    if provider == "anthropic":
        from app.runtime.adapters.anthropic import AnthropicClient
        return AnthropicClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    if provider == "openai":
        from app.runtime.adapters.openai import OpenAIClient
        return OpenAIClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    if provider == "perplexity":
        from app.runtime.adapters.perplexity import PerplexityClient
        return PerplexityClient(api_key=api_key, pricing_snapshot=pricing_snapshot, base_url=base_url)
    raise ValueError(f"Unknown LLM provider: {provider!r}. Expected one of: anthropic, openai, perplexity")


# ── Re-exports for backward compatibility ─────────────────────────────────────
# Existing imports like `from app.runtime.llm_client import AnthropicClient` continue to work.

from app.runtime.adapters.anthropic import AnthropicClient as AnthropicClient  # noqa: E402, F401
from app.runtime.adapters.openai import OpenAIClient as OpenAIClient            # noqa: E402, F401
from app.runtime.adapters.perplexity import PerplexityClient as PerplexityClient  # noqa: E402, F401
