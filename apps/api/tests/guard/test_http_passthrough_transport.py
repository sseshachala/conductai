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


def _portkey_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="portkey-primary",
        transport="http_passthrough",
        integration="portkey",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/portkey",
        # PR 4 review — portkey needs an upstream selector alongside
        # the gateway key. Default the test target to a virtual key so
        # the required-selector guard doesn't trip in the happy paths.
        provider_options={"virtual_key": "vk-openai-prod"},
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _helicone_openai_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="helicone-openai-primary",
        transport="http_passthrough",
        integration="helicone_openai",
        model="gpt-4o",
        credential_ref=f"vault://{ENV}/helicone",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _helicone_anthropic_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="helicone-anthropic-primary",
        transport="http_passthrough",
        integration="helicone_anthropic",
        model="claude-sonnet-4-6",
        credential_ref=f"vault://{ENV}/helicone",
    )
    defaults.update(overrides)
    return HTTPPassthroughTarget(**defaults)


def _azure_target(**overrides) -> HTTPPassthroughTarget:
    defaults = dict(
        id="azure-primary",
        transport="http_passthrough",
        integration="azure_openai",
        model="gpt-4o-prod-deploy",   # deployment name, NOT a model id
        credential_ref=f"vault://{ENV}/azure",
        endpoint="https://my-resource.openai.azure.com",
        provider_options={"api_version": "2024-06-01"},
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
async def test_portkey_chat_completions_uses_x_portkey_api_key_header(monkeypatch):
    """Portkey is OpenAI-compatible at /v1/chat/completions but uses a
    raw ``x-portkey-api-key`` header — NOT ``Authorization: Bearer``.
    Also lock: no OpenRouter attribution headers leak through, the
    target's model id replaces whatever the client sent, and the
    virtual-key upstream selector reaches the wire."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-pk"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_portkey_target(),
        operation="openai_chat_completions",
        payload={"model": "cond-alias", "messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "pk-live",
    )

    assert result == {"id": "chatcmpl-pk"}
    assert captured["url"] == "https://api.portkey.ai/v1/chat/completions"
    assert captured["headers"]["x-portkey-api-key"] == "pk-live"
    assert captured["headers"]["x-portkey-virtual-key"] == "vk-openai-prod"
    assert "authorization" not in {k.lower() for k in captured["headers"]}
    assert "HTTP-Referer" not in captured["headers"]
    import json as _json
    assert _json.loads(captured["content"])["model"] == "gpt-4o"


@pytest.mark.anyio("asyncio")
async def test_portkey_missing_upstream_selector_fails_closed(monkeypatch):
    """Portkey's gateway key alone doesn't route anywhere. Fail loudly
    with a config error instead of letting the request reach Portkey
    and getting a mystery 400."""
    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = AsyncMock(return_value=_FakeResponse(200, {}))
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    with pytest.raises(ValueError, match=r"virtual_key.*provider.*config"):
        await transport.execute(
            target=_portkey_target(provider_options={}),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "pk-live",
        )
    fake_client.post.assert_not_called()


@pytest.mark.anyio("asyncio")
async def test_portkey_provider_and_config_headers_reach_wire(monkeypatch):
    """``provider`` and ``config`` are the other two Portkey selectors;
    any one of the three satisfies the required-selector check and
    each maps to its documented header."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(headers=headers)
        return _FakeResponse(200, {"id": "ok"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_portkey_target(provider_options={"provider": "openai", "config": "cfg_abc"}),
        operation="openai_chat_completions",
        payload={"messages": []},
        credential_resolver=lambda ref: "pk-live",
    )

    assert captured["headers"]["x-portkey-provider"] == "openai"
    assert captured["headers"]["x-portkey-config"] == "cfg_abc"


@pytest.mark.anyio("asyncio")
async def test_helicone_openai_uses_two_key_auth(monkeypatch):
    """Helicone-OpenAI: Helicone-Auth carries the observability key,
    Authorization carries the upstream OpenAI key. URL rewrites to
    Helicone's mirror, but the vendor still sees a normal OpenAI-shape
    chat completion body. Model swap happens as usual."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-hel"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_helicone_openai_target(),
        operation="openai_chat_completions",
        payload={"model": "cond-alias", "messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-hel-live",
        vendor_credential_resolver=lambda ref: "sk-openai-live",
    )

    assert result == {"id": "chatcmpl-hel"}
    assert captured["url"] == "https://oai.helicone.ai/v1/chat/completions"
    assert captured["headers"]["Helicone-Auth"] == "Bearer sk-hel-live"
    assert captured["headers"]["authorization"] == "Bearer sk-openai-live"
    import json as _json
    assert _json.loads(captured["content"])["model"] == "gpt-4o"


@pytest.mark.anyio("asyncio")
async def test_helicone_anthropic_uses_x_api_key_and_version_header(monkeypatch):
    """Helicone-Anthropic: Helicone-Auth: Bearer + x-api-key (NO Bearer)
    for the Anthropic upstream + the mandatory anthropic-version static
    header. URL rewrites to Helicone's Anthropic mirror at /messages."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "msg_hel"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_helicone_anthropic_target(),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "sk-hel-live",
        vendor_credential_resolver=lambda ref: "sk-ant-live",
    )

    assert result == {"id": "msg_hel"}
    assert captured["url"] == "https://anthropic.helicone.ai/v1/messages"
    assert captured["headers"]["Helicone-Auth"] == "Bearer sk-hel-live"
    assert captured["headers"]["x-api-key"] == "sk-ant-live"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert "authorization" not in {k.lower() for k in captured["headers"]}


@pytest.mark.anyio("asyncio")
async def test_helicone_missing_vendor_key_fails_closed():
    """Fail-closed if the bridge didn't supply a vendor resolver, or
    the vendor resolver returns empty."""
    transport = HTTPPassthroughTransport()

    with pytest.raises(ValueError, match=r"vendor_credential_resolver"):
        await transport.execute(
            target=_helicone_openai_target(),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-hel",
        )

    with pytest.raises(ValueError, match=r"empty"):
        await transport.execute(
            target=_helicone_openai_target(),
            operation="openai_chat_completions",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-hel",
            vendor_credential_resolver=lambda ref: "",
        )


@pytest.mark.anyio("asyncio")
async def test_azure_openai_url_has_deployment_and_api_version(monkeypatch):
    """Azure URL is per-tenant: <endpoint>/openai/deployments/<deployment>/
    chat/completions?api-version=<version>. Auth uses raw ``api-key``
    header, NOT ``Authorization: Bearer``. Deployment lives in
    target.model; api-version lives in target.provider_options and is
    added as a query parameter with underscore→dash conversion."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers, content=content)
        return _FakeResponse(200, {"id": "chatcmpl-az"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_azure_target(),
        operation="openai_chat_completions",
        payload={"model": "cond-alias", "messages": [{"role": "user", "content": "hi"}]},
        credential_resolver=lambda ref: "az-key-live",
    )

    assert result == {"id": "chatcmpl-az"}
    assert captured["url"] == (
        "https://my-resource.openai.azure.com"
        "/openai/deployments/gpt-4o-prod-deploy/chat/completions"
        "?api-version=2024-06-01"
    )
    assert captured["headers"]["api-key"] == "az-key-live"
    assert "authorization" not in {k.lower() for k in captured["headers"]}
    import json as _json
    assert _json.loads(captured["content"])["model"] == "gpt-4o-prod-deploy"


@pytest.mark.anyio("asyncio")
async def test_azure_deployment_name_is_url_encoded(monkeypatch):
    """PR 6 review — a deployment name with slashes / spaces would
    otherwise smuggle path segments into the Azure URL. Quote per RFC
    3986 unreserved so the request lands at the literal deployment."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url)
        return _FakeResponse(200, {})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    await transport.execute(
        target=_azure_target(model="my deploy/name+special"),
        operation="openai_chat_completions",
        payload={"messages": []},
        credential_resolver=lambda ref: "az-key",
    )
    # Space → %20, slash → %2F, plus → %2B — no raw segments smuggled.
    assert "/openai/deployments/my%20deploy%2Fname%2Bspecial/chat/completions" in captured["url"]


@pytest.mark.anyio("asyncio")
async def test_azure_openai_endpoint_override_does_not_warn(monkeypatch):
    """Azure is per-tenant, so an endpoint override is REQUIRED, not
    accidental. The endpoint-override warning that fires for pinned
    integrations must NOT fire for Azure."""

    async def _fake_post(url, headers, content):
        return _FakeResponse(200, {"id": "x"})

    transport = HTTPPassthroughTransport()
    fake_client = MagicMock()
    fake_client.post = _fake_post
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    warnings: list[dict] = []
    import app.runtime.http_passthrough_transport as mod
    monkeypatch.setattr(mod.log, "warning", lambda ev, **kw: warnings.append({"event": ev, **kw}))

    await transport.execute(
        target=_azure_target(),
        operation="openai_chat_completions",
        payload={"messages": []},
        credential_resolver=lambda ref: "az-key",
    )
    override_warnings = [
        w for w in warnings
        if w["event"] == "gateway.v2.http_passthrough.endpoint_override_ignored"
    ]
    assert override_warnings == []


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
    """Custom is not yet registered in ``_INTEGRATION_ENDPOINTS`` (PR 7).
    Fail loudly with the specific integration name, don't guess at a URL."""
    transport = HTTPPassthroughTransport()
    with pytest.raises(UnsupportedPassthroughIntegration, match=r"custom"):
        await transport.execute(
            target=_openrouter_target(integration="custom"),
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
    # Custom (PR 7) still not registered on this branch.
    assert integration_certifies_operation("custom", "openai_chat_completions") is False
