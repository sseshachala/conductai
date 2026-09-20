"""End-to-end streaming test for /gateway/v1/completions (#2144 follow-up).

Proves the shim now accepts ``stream: true`` and forwards it through the
same v2 executor path used by the SDK-shaped OpenAI route. The response
is ``text/event-stream``; the caller iterates the raw SSE bytes.

Fake path is a canned SSE stream (openai delta format), stubbed at the
``NativeHTTPTransport.execute`` seam inline so it only affects this
test — the module-level fixture in ``conftest.py`` still returns a
non-streaming dict for the other integration tests.
"""
from __future__ import annotations

from typing import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient

from app.runtime.native_http_transport import StreamingUpstream


class _CannedByteStream(httpx.AsyncByteStream):
    """Emit a pre-baked list of chunks then close.

    httpx.Response accepts anything implementing ``AsyncByteStream``
    (``__aiter__`` + ``aclose``), so a tiny in-memory chunker is enough
    to fake an OpenAI SSE response.
    """

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


_SSE_CHUNKS: list[bytes] = [
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{"role":"assistant"},"index":0}]}\n\n',
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{"content":"pong"},"index":0}]}\n\n',
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
    b'data: [DONE]\n\n',
]


@pytest.fixture()
def stub_streaming_transport(monkeypatch: pytest.MonkeyPatch):
    """Return a canned SSE stream from NativeHTTPTransport.execute when
    called with ``stream=True``. Falls through to the module-level
    non-streaming stub for stream=False so tests can share a fixture set.
    """
    captured: list[dict] = []

    async def _fake_execute(self, *, target, operation, payload,
                            credential_resolver, stream=False,
                            client_headers=None):
        captured.append({
            "target_id": target.id,
            "target_model": target.model,
            "operation": operation,
            "stream": stream,
        })
        if not stream:
            return {"stub": "non-streaming path — should not be reached in this test"}
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_CannedByteStream(list(_SSE_CHUNKS)),
        )
        return StreamingUpstream(
            status_code=200,
            headers={"content-type": "text/event-stream"},
            response=response,
            provider=target.provider,
        )

    monkeypatch.setattr(
        "app.runtime.native_http_transport.NativeHTTPTransport.execute",
        _fake_execute,
    )
    return captured


def test_stream_true_returns_sse_response(
    seeded_profile, gateway_app, stub_streaming_transport,
) -> None:
    client = TestClient(gateway_app)

    with client.stream(
        "POST",
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
        json={
            "profile": seeded_profile["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            "stream": True,
        },
    ) as resp:
        assert resp.status_code == 200, resp.read()
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type, (
            f"expected SSE content-type, got {content_type!r}"
        )
        body = b"".join(resp.iter_bytes())

    # Every SSE chunk we canned lands in the client's body verbatim —
    # the executor forwards upstream bytes untouched for streaming.
    for chunk in _SSE_CHUNKS:
        assert chunk in body, (
            f"expected SSE chunk {chunk!r} in response body; got "
            f"{body[:200]!r}..."
        )

    # And the transport was called with stream=True — proves the shim
    # actually propagated the flag, not silently coerced it to False.
    assert len(stub_streaming_transport) == 1, stub_streaming_transport
    call = stub_streaming_transport[0]
    assert call["stream"] is True, call
    assert call["operation"] == "openai_chat_completions", call


def test_stream_false_still_returns_json_after_streaming_support_lands(
    seeded_profile, gateway_app,
) -> None:
    """The non-streaming path must remain unchanged once stream=true is
    supported — regression guard against a future refactor that
    accidentally forces every request through the SSE path.
    """
    client = TestClient(gateway_app)

    resp = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
        json={
            "profile": seeded_profile["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
            # stream deliberately omitted — same as stream: false
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers.get("content-type", "").startswith("application/json")
    payload = resp.json()
    assert payload.get("object") == "chat.completion", payload
