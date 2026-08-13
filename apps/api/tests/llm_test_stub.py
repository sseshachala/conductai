"""Deterministic LLM stub — Group C of epic #1092.

Import + call `install_llm_stub()` from any test that hits brain_block
or the LLM client directly. Returns canned responses with realistic
token accounting so downstream analytics/audit paths exercise fully.

Rationale: real LLM calls in CI need an ANTHROPIC_API_KEY, cost money,
and are non-deterministic. The stub gives us a fully-covered execution
path without any of those.

Usage:
    from tests.llm_test_stub import install_llm_stub

    def test_something():
        with install_llm_stub() as calls:
            ... # code that eventually calls AnthropicClient(...).create(...)
        assert len(calls) == 1
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import patch

from app.runtime.llm_client import LLMResponse, LLMTextBlock, LLMUsage


DEFAULT_TEXT = "Stubbed LLM response — test mode."


def _canned_response(text: str = DEFAULT_TEXT) -> LLMResponse:
    return LLMResponse(
        content=[LLMTextBlock(type="text", text=text)],
        stop_reason="end_turn",
        usage=LLMUsage(input_tokens=42, output_tokens=17),
        cost_usd=0.001,
        _raw_content=[{"type": "text", "text": text}],
    )


class _StubClient:
    """Drop-in stand-in for AnthropicClient / OpenAIClient / PerplexityClient.

    Records every create() call so tests can assert on prompt shape,
    tool selections, etc. Returns the canned response.
    """

    def __init__(self, calls: list, response_text: str = DEFAULT_TEXT, **_ignored):
        self.calls = calls
        self._response_text = response_text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _canned_response(self._response_text)

    def make_assistant_turn(self, response: LLMResponse) -> list[dict]:
        return [{"role": "assistant", "content": response.content}]


@contextmanager
def install_llm_stub(response_text: str = DEFAULT_TEXT) -> Iterator[list[dict]]:
    """Context manager that swaps every concrete LLM client with the stub.
    Yields a list that fills with every create() call's kwargs."""
    calls: list[dict] = []

    def _factory(**kwargs):
        return _StubClient(calls, response_text=response_text, **kwargs)

    targets = [
        "app.runtime.adapters.anthropic.AnthropicClient",
        "app.runtime.adapters.openai.OpenAIClient",
        "app.runtime.adapters.perplexity.PerplexityClient",
        # brain_block imports these by short name — patch there too.
        "app.runtime.blocks.brain_block.AnthropicClient",
        "app.runtime.blocks.brain_block.OpenAIClient",
        "app.runtime.blocks.brain_block.PerplexityClient",
    ]
    patchers = [patch(t, _factory) for t in targets]
    for p in patchers:
        p.start()
    try:
        yield calls
    finally:
        for p in patchers:
            p.stop()
