"""Pin the LLM test stub's shape so downstream callers can rely on it."""
from __future__ import annotations

from tests.llm_test_stub import install_llm_stub


def test_stub_returns_canned_response():
    with install_llm_stub("hello from stub") as calls:
        # Import inside the with-block so the patched symbol is resolved.
        from app.runtime.adapters.anthropic import AnthropicClient

        client = AnthropicClient(api_key="not-used")
        resp = client.create(messages=[{"role": "user", "content": "ignored"}])

    assert resp.content[0].text == "hello from stub"
    assert resp.stop_reason == "end_turn"
    assert resp.usage.input_tokens == 42
    assert resp.usage.output_tokens == 17
    assert resp.cost_usd == 0.001
    assert len(calls) == 1
    assert calls[0]["messages"][0]["content"] == "ignored"


def test_stub_swaps_all_three_providers():
    with install_llm_stub() as calls:
        from app.runtime.adapters.anthropic import AnthropicClient
        from app.runtime.adapters.openai import OpenAIClient
        from app.runtime.adapters.perplexity import PerplexityClient

        for cls in (AnthropicClient, OpenAIClient, PerplexityClient):
            cls(api_key="x").create(messages=[{"role": "user", "content": "hi"}])

    assert len(calls) == 3
