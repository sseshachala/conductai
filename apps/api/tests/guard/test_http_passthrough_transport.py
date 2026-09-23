"""Contract tests for HTTPPassthroughTransport (PR 5).

Locks the runtime invariants for the passthrough executor. The launch
integration is OpenRouter — Portkey / Helicone / Azure / Custom land in
follow-up PRs.

Structural invariants:

- Registered integration + certified operation → HTTP forward with the
  integration's auth header shape (Bearer for OpenRouter).
- Payload's ``model`` field is replaced by the target's model id so
  the vendor sees the model the admin published, not a cond-* alias.
- Empty credential raises ``ValueError`` before the wire (belt-and-
  braces with the capability catalog + credential resolver).
- Unregistered integration raises ``UnsupportedPassthroughIntegration``
  before the wire — the transport never guesses an endpoint.
- Streaming is refused in PR 5 (native_http covers streaming; passthrough
  streaming lands in a follow-up).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.guard.gateway_config import HTTPPassthroughTarget
from app.runtime.http_passthrough_transport import (
    HTTPPassthroughTransport,
    UnsupportedPassthroughIntegration,
    integration_certifies_operation,
)


ENV = "11111111-1111-1111-1111-111111111111"


def _openrouter_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="openrouter-primary",
        transport="http_passthrough",
        integration="openrouter",
        model="anthropic/claude-sonnet",
        credential_ref=f"vault://{ENV}/openrouter",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _custom_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="custom-primary",
        transport="http_passthrough",
        integration="custom",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/custom",
        endpoint="https://my-llm-proxy.example.com/v1",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


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
async def test_openrouter_chat_completions_hits_correct_url_with_bearer(monkeypatch):
    """OpenRouter is OpenAI-compatible at /api/v1/chat/completions with
    ``Authorization: Bearer <key>``. Also carries ``HTTP-Referer`` +
    ``X-Title`` for OpenRouter's attribution dashboards — without
    them our traffic lands in their "unknown" analytics bucket."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-x"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_openrouter_target(),
        operation="openai_chat_completions",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-or-live",
    )
    assert result == {"id": "chatcmpl-x"}
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-or-live"
    # Attribution headers reach the wire.
    assert captured["headers"]["HTTP-Referer"] == "https://conductai.ai"
    assert captured["headers"]["X-Title"] == "Conduct AI Gateway"


@pytest.mark.anyio("asyncio")
async def test_custom_defaults_to_bearer_authorization_and_target_endpoint(monkeypatch):
    """Custom with no provider_options overrides falls back to the
    Bearer + authorization defaults. URL comes from target.endpoint +
    the operation's standard suffix."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-custom"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_custom_target(),
        operation="openai_chat_completions",
        payload={"model": "cond-alias", "messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-live",
    )

    assert result == {"id": "chatcmpl-custom"}
    assert captured["url"] == "https://my-llm-proxy.example.com/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-live"
    # No accidental static extra headers leaked from other integrations.
    assert "HTTP-Referer" not in captured["headers"]
    assert "Helicone-Auth" not in captured["headers"]


@pytest.mark.anyio("asyncio")
async def test_custom_provider_options_override_auth_header_and_prefix(monkeypatch):
    """Admin sets auth_header=x-api-key + bearer_prefix=False +
    extra_headers={X-Team: platform}. All three land on the wire in
    place of / in addition to the defaults."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers)
        return _FakeResponse(200, {"id": "x"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_custom_target(provider_options={
            "auth_header":    "x-api-key",
            "bearer_prefix":  False,
            "extra_headers":  {"X-Team": "platform", "X-Env": "prod"},
        }),
        operation="anthropic_messages",
        payload={"messages": []},
        credential_resolver=lambda ref: "sk-raw",
    )

    # Path picks the Anthropic-shape suffix from the pinned operation_paths.
    assert captured["url"] == "https://my-llm-proxy.example.com/v1/messages"
    # Raw key in the admin-chosen header, no Bearer.
    assert captured["headers"]["x-api-key"] == "sk-raw"
    assert "authorization" not in {k.lower() for k in captured["headers"]}
    # Extra static headers reach the wire.
    assert captured["headers"]["X-Team"] == "platform"
    assert captured["headers"]["X-Env"] == "prod"


@pytest.mark.anyio("asyncio")
async def test_pinned_integration_ignores_endpoint_override_with_warning(monkeypatch):
    """A target for a pinned integration (OpenRouter) that carries a
    ``target.endpoint`` gets its endpoint silently ignored — the URL
    was pinned at integration-registration time. That's the intended
    behavior, but the transport must WARN so the admin knows their
    endpoint value didn't take effect.
    """
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "x"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    # Capture warnings from the transport's structlog logger. Structlog
    # ends up going through stdlib logging in tests, but the event
    # keyword is the source of truth — spy on the log method directly.
    warnings: list[dict] = []
    def _warning(event, **fields):
        warnings.append({"event": event, **fields})
    import app.runtime.http_passthrough_transport as mod
    monkeypatch.setattr(mod.log, "warning", _warning)

    await transport.execute(
        target=_openrouter_target(endpoint="https://not-actually-used.example.com/v1"),
        operation="openai_chat_completions",
        payload={"messages": []},
        credential_resolver=lambda ref: "sk-or",
    )
    # Request went to OpenRouter's pinned URL, NOT the target.endpoint.
    assert captured["url"].startswith("https://openrouter.ai/")

    # Exactly one endpoint-override warning fired, carrying enough
    # detail for an admin to find the misconfigured target.
    ignored = [
        w for w in warnings
        if w["event"] == "gateway.v2.http_passthrough.endpoint_override_ignored"
    ]
    assert len(ignored) == 1, warnings
    assert ignored[0]["target_id"] == "openrouter-primary"
    assert ignored[0]["ignored_endpoint"] == "https://not-actually-used.example.com/v1"


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
async def test_streaming_refused_in_pr5():
    """Streaming through passthrough is a follow-up PR. Refuse loudly
    with the fix hint: put a native_http target ahead of this
    passthrough one."""
    transport = HTTPPassthroughTransport()
    with pytest.raises(NotImplementedError, match=r"native_http"):
        await transport.execute(
            target=_openrouter_target(),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-or",
            stream=True,
        )


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
async def test_unregistered_integration_raises_before_upstream():
    """Portkey / Helicone / Azure / Custom aren't registered in
    ``_INTEGRATION_ENDPOINTS`` yet. Fail loudly with the specific
    integration name, don't guess at a URL."""
    transport = HTTPPassthroughTransport()
    with pytest.raises(UnsupportedPassthroughIntegration, match=r"portkey"):
        await transport.execute(
            target=_openrouter_target(integration="portkey"),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-portkey",
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
    # PR 7 — Custom certified for every launch operation.
    assert integration_certifies_operation("custom", "openai_chat_completions") is True
    assert integration_certifies_operation("custom", "openai_responses") is True
    assert integration_certifies_operation("custom", "anthropic_messages") is True
    assert integration_certifies_operation("custom", "anthropic_count_tokens") is True
    # Portkey (PR 4) / Helicone (PR 5) / Azure (PR 6) not registered on this branch.
    assert integration_certifies_operation("portkey", "openai_chat_completions") is False
