"""Contract tests for NativeHTTPTransport (PR 2 + PR 2.5 streaming).

Locks the transport's runtime invariants:

- Vendor endpoint + auth header shape matches the provider.
- Payload's ``model`` field is replaced by the target's own model id
  before the upstream call fires — the client's cond-* identifier
  never reaches the vendor.
- Credential comes from the caller-supplied resolver, is only used
  for the duration of the single call, and an empty resolver return
  raises before any HTTP touches the wire.
- Streaming (PR 2.5) returns a ``StreamingUpstream`` with the live
  httpx.Response; 4xx/5xx before body is raised as HTTPStatusError so
  the coordinator's retry classifier walks it exactly like a
  non-streaming upstream error.
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


class _FakeStreamResponse:
    """A stand-in for the still-open httpx.Response returned by
    ``client.send(request, stream=True)``. Records ``aclose()`` so tests
    can assert cleanup, exposes an async ``aiter_bytes`` generator, and
    lets tests inject an error status + body payload."""

    def __init__(self, status_code=200, chunks=None, error_body=b""):
        self.status_code = status_code
        self.headers = {"content-type": "text/event-stream"}
        self._chunks = list(chunks or [])
        self._error_body = error_body
        self.aclose_calls = 0
        self.aread_calls = 0

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk

    async def aread(self):
        self.aread_calls += 1
        return self._error_body

    async def aclose(self):
        self.aclose_calls += 1


@pytest.mark.anyio("asyncio")
async def test_streaming_returns_streaming_upstream(monkeypatch):
    """PR 2.5 — stream=True returns a StreamingUpstream carrying the
    live httpx.Response. Coordinator gets a happy-path return the
    moment headers are past the 400 check, meaning no retry after
    headers."""
    from app.runtime.native_http_transport import StreamingUpstream

    fake_response = _FakeStreamResponse(
        status_code=200,
        chunks=[b"data: {\"delta\":\"hi\"}\n\n", b"data: [DONE]\n\n"],
    )
    captured_request: dict = {}

    def _build_request(method, url, headers, content):
        captured_request.update(method=method, url=url, headers=headers, content=content)
        return MagicMock(spec_set=["method", "url"])

    async def _fake_send(request, stream):
        assert stream is True, "coordinator must ask for a live stream"
        return fake_response

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.build_request = _build_request
    fake_client.send = _fake_send
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    result = await transport.execute(
        target=_target(),
        operation="anthropic_messages",
        payload={"messages": [{"role": "user", "content": "hi"}], "stream": True},
        credential_resolver=lambda ref: "sk-ant-live",
        stream=True,
    )
    assert isinstance(result, StreamingUpstream)
    assert result.status_code == 200
    assert result.headers["content-type"] == "text/event-stream"
    assert result.provider == "anthropic"
    # Body payload asked for stream=true.
    import json
    body = json.loads(captured_request["content"])
    assert body["stream"] is True


@pytest.mark.anyio("asyncio")
async def test_streaming_upstream_4xx_raises_httpstatuserror(monkeypatch):
    """4xx from the vendor during a streaming attempt must raise
    HTTPStatusError (with response.status_code set) so the coordinator
    can retry the next target. The still-open response must be closed
    before the exception propagates — otherwise the pool leaks a slot."""
    import httpx

    fake_response = _FakeStreamResponse(status_code=401, error_body=b'{"error":"bad key"}')

    def _build_request(method, url, headers, content):
        return MagicMock(spec_set=["method", "url"])

    async def _fake_send(request, stream):
        return fake_response

    transport = NativeHTTPTransport()
    fake_client = MagicMock()
    fake_client.build_request = _build_request
    fake_client.send = _fake_send
    monkeypatch.setattr(transport, "_get_client", AsyncMock(return_value=fake_client))

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        await transport.execute(
            target=_target(),
            operation="anthropic_messages",
            payload={"messages": []},
            credential_resolver=lambda ref: "sk-fake",
            stream=True,
        )
    assert excinfo.value.response.status_code == 401
    # Cleanup: response was aread + aclose'd before we raised, so the
    # httpx pool doesn't leak.
    assert fake_response.aread_calls == 1
    assert fake_response.aclose_calls == 1


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
