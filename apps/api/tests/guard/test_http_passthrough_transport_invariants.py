"""Contract tests for HTTPPassthroughTransport (PR 5) — integration-agnostic
invariants: model replacement, streaming ownership, empty-credential and
unregistered / uncertified integration refusal before the wire.

Split from ``test_http_passthrough_transport.py``; shared target builders
live in ``_http_passthrough_helpers.py``.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.runtime.http_passthrough_transport import (
    HTTPPassthroughTransport,
    UnsupportedPassthroughIntegration,
    integration_certifies_operation,
)

from tests.guard._http_passthrough_helpers import (
    _FakeResponse,
    _custom_target,
    _openrouter_target,
)


@pytest.mark.anyio("asyncio")
async def test_client_model_field_is_replaced_by_target_model(monkeypatch):
    """The client sent a cond-* alias; the vendor must see the
    published model id (``anthropic/claude-sonnet``)."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        import json
        captured.update(body=json.loads(content))
        return _FakeResponse(200, {"id": "x"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_openrouter_target(model="anthropic/claude-sonnet"),
        operation="openai_chat_completions",
        payload={
            "model": "cond-abc12345-coding",   # client's routing alias
            "messages": [{"role": "user", "content": "hi"}],
        },
        credential_resolver=lambda ref: "sk-or-live",
    )
    assert captured["body"]["model"] == "anthropic/claude-sonnet"


@pytest.mark.anyio("asyncio")
async def test_streaming_returns_owned_upstream():
    import httpx
    from app.runtime.native_http_transport import StreamingUpstream
    transport = HTTPPassthroughTransport()
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, content=b"data: [DONE]\n\n", headers={"content-type": "text/event-stream"})
    )) as client:
        transport._client = client
        result = await transport.execute(
            target=_openrouter_target(),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-or",
            stream=True,
        )
        assert isinstance(result, StreamingUpstream)
        assert b"[DONE]" in b"".join([chunk async for chunk in result.response.aiter_bytes()])
        await result.response.aclose()
        assert result.response.is_closed


@pytest.mark.anyio("asyncio")
async def test_empty_credential_raises_before_calling_upstream():
    """Symmetric with the other transports — never emit an empty auth
    header, so the vendor doesn't see an ambiguous unauthenticated
    call and treat it as their public tier."""
    transport = HTTPPassthroughTransport()
    with pytest.raises(ValueError, match=r"credential_resolver returned empty"):
        await transport.execute(
            target=_openrouter_target(),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "",
        )


@pytest.mark.anyio("asyncio")
async def test_unregistered_integration_raises_before_upstream(monkeypatch):
    """Belt-and-braces: if publish somehow lets an integration through
    that has no ``_INTEGRATION_ENDPOINTS`` entry, the transport must
    fail loudly at request time — not guess a URL. All six integrations
    are registered post-PR-7, so we simulate the drift by removing
    ``custom`` from the map for this one test."""
    import app.runtime.http_passthrough_transport as mod
    orig = mod._INTEGRATION_ENDPOINTS
    monkeypatch.setattr(
        mod, "_INTEGRATION_ENDPOINTS",
        {k: v for k, v in orig.items() if k != "custom"},
    )
    transport = HTTPPassthroughTransport()
    with pytest.raises(UnsupportedPassthroughIntegration, match=r"custom"):
        await transport.execute(
            target=_custom_target(),  # valid custom target
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-custom",
        )


@pytest.mark.anyio("asyncio")
async def test_uncertified_operation_for_registered_integration_raises(monkeypatch):
    """OpenRouter is registered for openai_chat_completions only in
    PR 5. Asking for anthropic_messages against openrouter must fail
    (belt-and-braces — publish catalog should have caught this)."""
    transport = HTTPPassthroughTransport()
    with pytest.raises(ValueError, match=r"anthropic_messages"):
        await transport.execute(
            target=_openrouter_target(),
            operation="anthropic_messages",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-or",
        )


def test_integration_certifies_operation_helper():
    """The public helper the capability catalog can use to double-
    check the runtime matrix. Guards against catalog-vs-runtime drift."""
    assert integration_certifies_operation("openrouter", "openai_chat_completions") is True
    assert integration_certifies_operation("openrouter", "anthropic_messages") is False
    assert integration_certifies_operation("portkey", "openai_chat_completions") is True
    assert integration_certifies_operation("portkey", "anthropic_messages") is False
    assert integration_certifies_operation("helicone_openai", "openai_chat_completions") is True
    assert integration_certifies_operation("helicone_openai", "anthropic_messages") is False
    assert integration_certifies_operation("helicone_anthropic", "anthropic_messages") is True
    assert integration_certifies_operation("helicone_anthropic", "openai_chat_completions") is False
    assert integration_certifies_operation("azure_openai", "openai_chat_completions") is True
    assert integration_certifies_operation("azure_openai", "anthropic_messages") is False
    # PR 7 — Custom transport CAN serve any launch operation (per-protocol
    # publish restriction is enforced separately via ``_CUSTOM_OPS_BY_PROTOCOL``
    # in the capability catalog).
    assert integration_certifies_operation("custom", "openai_chat_completions") is True
    assert integration_certifies_operation("custom", "openai_responses") is True
    assert integration_certifies_operation("custom", "anthropic_messages") is True
    assert integration_certifies_operation("custom", "anthropic_count_tokens") is True
