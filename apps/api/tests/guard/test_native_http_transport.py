"""Contract tests for NativeHTTPTransport (PR 2).

Locks the transport's runtime invariants:

- Vendor endpoint + auth header shape matches the provider.
- Payload's ``model`` field is replaced by the target's own model id
  before the upstream call fires — the client's cond-* identifier
  never reaches the vendor.
- Credential comes from the caller-supplied resolver, is only used
  for the duration of the single call, and an empty resolver return
  raises before any HTTP touches the wire.
- Streaming is refused symmetrically with the LiteLLM transport
  (Phase 1 non-streaming only).
- Unknown provider / unsupported operation raise ValueError, not
  silent fallthrough — capability catalog should have caught these
  at publish, but belt-and-braces at execute time.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.guard.gateway_config import NativeHTTPTarget
from app.runtime.native_http_transport import NativeHTTPTransport


ENV = "11111111-1111-1111-1111-111111111111"


def _target(**overrides) -> NativeHTTPTarget:
    defaults = dict(
        id="primary",
        transport="native_http",
        provider="anthropic",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/anthropic",
        provider_options={},
    )
    defaults.update(overrides)
    return NativeHTTPTarget(**defaults)


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None):
        self.status_code = status_code
        self._json = json_body or {}

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx
            raise httpx.HTTPStatusError(
                "upstream error",
                request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )


@pytest.mark.anyio("asyncio")
async def test_anthropic_messages_calls_v1_messages_with_x_api_key(monkeypatch):
    """Anthropic auth is ``x-api-key`` (not ``Authorization: Bearer``),
    and the /v1/messages path is used for anthropic_messages."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"content": "ok"})

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_target(),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-ant-live",
    )
    assert result == {"content": "ok"}
    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-live"
    assert "Bearer" not in captured["headers"].get("x-api-key", "")


@pytest.mark.anyio("asyncio")
async def test_openai_chat_uses_authorization_bearer(monkeypatch):
    """OpenAI auth is ``Authorization: Bearer <key>``."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-x"})

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_target(provider="openai", model="gpt-4o"),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-openai-live",
    )
    assert captured["url"] == "https://api.openai.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-openai-live"


@pytest.mark.anyio("asyncio")
async def test_client_model_field_is_replaced_by_target_model(monkeypatch):
    """The client's payload carries a cond-<code>-<alias> in ``model:``
    or a client-facing alias. Upstream needs the real vendor model id
    the target advertises."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        import json
        captured.update(body=json.loads(content))
        return _FakeResponse(200, {"content": "ok"})

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_target(model="claude-sonnet-4-6"),
        operation="anthropic_messages",
        payload={
            "model": "cond-abc12345-coding",   # client's routing id
            "messages": [{"role": "user", "content": "hi"}],
        },
        credential_resolver=lambda ref: "sk-fake",
    )
    assert captured["body"]["model"] == "claude-sonnet-4-6"
    # Everything else preserved
    assert captured["body"]["messages"] == [{"role": "user", "content": "hi"}]


@pytest.mark.anyio("asyncio")
async def test_streaming_refused():
    """Streaming isn't supported in this PR — coordinator refuses at
    plan build time; belt-and-braces at the transport."""
    transport = NativeHTTPTransport()
    with pytest.raises(NotImplementedError, match=r"streaming"):
        await transport.execute(
            target=_target(),
            operation="anthropic_messages",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-fake",
            stream=True,
        )


@pytest.mark.anyio("asyncio")
async def test_empty_credential_raises_before_calling_upstream():
    """Symmetric with LiteLLM transport — an empty resolver return is
    a config error, surface it before the wire so we never leak an
    ambiguous empty auth header."""
    transport = NativeHTTPTransport()
    with pytest.raises(ValueError, match=r"credential_resolver returned empty"):
        await transport.execute(
            target=_target(),
            operation="anthropic_messages",
            payload={"messages": []},
            credential_resolver=lambda ref: "",
        )


@pytest.mark.anyio("asyncio")
async def test_unknown_provider_raises_before_calling_upstream():
    """Publish catches uncertified providers via the capability catalog,
    but the transport double-checks so a bad publish can't silently
    hit an arbitrary endpoint."""
    transport = NativeHTTPTransport()
    with pytest.raises(ValueError, match=r"no vendor endpoint registered"):
        await transport.execute(
            target=_target(provider="perplexity"),
            operation="anthropic_messages",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-fake",
        )
