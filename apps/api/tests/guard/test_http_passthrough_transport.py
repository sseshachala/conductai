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
    # Raw api-key header, no Bearer prefix, no stray Authorization.
    assert captured["headers"]["api-key"] == "az-key-live"
    assert "authorization" not in {k.lower() for k in captured["headers"]}
    # Body model still swapped to deployment name (harmless for Azure
    # which reads deployment from the URL, but keeps behaviour uniform).
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
    # Space encoded to %20, slash to %2F, plus to %2B — no raw path segments smuggled in.
    assert "/openai/deployments/my%20deploy%2Fname%2Bspecial/chat/completions" in captured["url"]


@pytest.mark.anyio("asyncio")
async def test_azure_openai_endpoint_override_does_not_warn(monkeypatch):
    """Azure is per-tenant, so an endpoint override is REQUIRED, not
    accidental. The endpoint-override warning that fires for pinned
    integrations must NOT fire for Azure."""
    captured: dict = {}

    async def _fake_post(url, headers, content):
        captured.update(url=url, headers=headers)
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
    assert integration_certifies_operation("azure_openai", "openai_chat_completions") is True
    assert integration_certifies_operation("azure_openai", "anthropic_messages") is False
    # Portkey (PR 4) + Helicone (PR 5) + Custom (PR 7) not registered on this branch.
    assert integration_certifies_operation("portkey", "openai_chat_completions") is False
