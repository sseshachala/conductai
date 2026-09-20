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

import time
from typing import AsyncIterator

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

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


_STREAM_PROMPT_TOKENS = 8
_STREAM_COMPLETION_TOKENS = 5


_SSE_CHUNKS: list[bytes] = [
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{"role":"assistant"},"index":0}]}\n\n',
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{"content":"pong"},"index":0}]}\n\n',
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[{"delta":{},"index":0,"finish_reason":"stop"}]}\n\n',
    # Final usage chunk — OpenAI only emits this when the client sends
    # stream_options.include_usage=true. Reviewer P1 on the streaming PR:
    # without server-side injection of that option, audit + budget
    # settlement carry zero tokens even for successful streams. This
    # test now proves the injection reaches upstream by shape-matching
    # the response format OpenAI uses.
    b'data: {"id":"chatcmpl-stream-1","object":"chat.completion.chunk",'
    b'"choices":[],"usage":{"prompt_tokens":8,"completion_tokens":5,'
    b'"total_tokens":13}}\n\n',
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
            # ``payload`` captures the request body the shim forwarded.
            # Tests assert stream_options is present so we can prove the
            # server-side usage-option injection actually made it to
            # this seam, not just to the pydantic model.
            "payload_stream_options": payload.get("stream_options"),
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


def _stream_audit_row(db, workspace_id: str) -> dict | None:
    """Fetch the newest gateway audit row for this workspace."""
    row = db.execute(
        text("""
            SELECT id::text, decision, execution_status, route,
                   tokens_before, tokens_after, ai_tool, agent_identity_id::text
            FROM guard_audit_events
            WHERE workspace_id = CAST(:ws AS uuid)
            ORDER BY ts DESC
            LIMIT 1
        """),
        {"ws": workspace_id},
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row.id,
        "decision": row.decision,
        "execution_status": row.execution_status,
        "route": row.route,
        "tokens_before": row.tokens_before,
        "tokens_after": row.tokens_after,
        "ai_tool": row.ai_tool,
        "agent_identity_id": row.agent_identity_id,
    }


def test_stream_true_returns_sse_response(
    seeded_profile, gateway_app, stub_streaming_transport, it_db,
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
    # Reviewer P1 (streaming): the shim MUST inject
    # stream_options.include_usage=true so OpenAI emits the final usage
    # chunk. Without this, audit rows and budget settlement carry zero
    # tokens for successful streams.
    assert call["payload_stream_options"] == {"include_usage": True}, (
        f"stream_options.include_usage=true must reach the transport for "
        f"stream=true — got {call['payload_stream_options']!r}"
    )


def test_streaming_finalizes_audit_with_token_counts_and_releases_admission(
    seeded_profile, gateway_app, stub_streaming_transport, it_db,
) -> None:
    """After a stream drains, the audit row must carry the token counts
    from the final usage chunk AND the admission slot must be released
    so subsequent traffic can flow.

    Both invariants together guard the reviewer's P1: streams that
    don't finalize audit + budget correctly are a silent gap in
    Flight Recorder and spend enforcement.
    """
    client = TestClient(gateway_app)

    # Drain the streaming response.
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
        assert resp.status_code == 200
        for _ in resp.iter_bytes():
            pass

    # Streaming audit finalize runs in the stream's ``on_close`` hook,
    # which fires when ASGI drains the body iterator. Give it a short
    # deadline to land in guard_audit_events. Deadline is generous so
    # a real regression fails here, not a flake.
    deadline = time.monotonic() + 5.0
    row: dict | None = None
    while time.monotonic() < deadline:
        it_db.expire_all()
        row = _stream_audit_row(it_db, seeded_profile["workspace_id"])
        if row is not None and (row["tokens_before"] or row["tokens_after"]):
            break
        time.sleep(0.05)

    assert row is not None, (
        "no guard_audit_events row landed for the streaming call — "
        "audit finalize is missing on the stream close path"
    )
    assert row["route"] == "/gateway/v1/completions", row
    assert row["decision"] == "allowed", row
    assert row["execution_status"] in {"ok", "success"}, row
    assert row["agent_identity_id"] == seeded_profile["agent_identity_id"], row

    # Token counts from the canned usage chunk MUST be present. If the
    # shim's stream_options.include_usage=true injection is missing, or
    # if the audit path drops the usage from the final chunk, both
    # columns land as None/0 — which is the exact silent gap this
    # test guards.
    assert row["tokens_before"] == _STREAM_PROMPT_TOKENS, (
        f"tokens_before={row['tokens_before']!r} expected "
        f"{_STREAM_PROMPT_TOKENS} from the canned usage chunk — usage "
        f"is not landing in audit rows for streaming calls"
    )
    assert row["tokens_after"] == _STREAM_COMPLETION_TOKENS, (
        f"tokens_after={row['tokens_after']!r} expected "
        f"{_STREAM_COMPLETION_TOKENS} from the canned usage chunk"
    )

    # Admission slot release invariant: a second non-streaming request
    # after the stream drains must succeed. If the stream's on_close
    # hook forgot to release the ticket, the workspace's inflight
    # counter stays elevated and eventually the slot cap refuses new
    # traffic. Firing a follow-up here is the cheapest proof the slot
    # was returned to the pool.
    followup = client.post(
        "/gateway/v1/completions",
        headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
        json={
            "profile": seeded_profile["profile_identifier"],
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 5,
        },
    )
    assert followup.status_code == 200, (
        f"follow-up request after stream drain returned "
        f"{followup.status_code}: {followup.text[:200]} — admission "
        f"slot may not have been released"
    )


# ─── client disconnect + upstream timeout ─────────────────────────────
#
# Both scenarios require the real ASGI receive/send loop so cancellation
# and mid-stream exceptions propagate the way they would over a network
# socket. Sync TestClient can't fake either — mid-stream close in sync
# mode leaves the ASGI app iterating on a body that never sees a
# disconnect message, so the ``on_close`` hook fires from normal drain
# rather than from cancellation, hiding the class of leak these tests
# exist to catch.
#
# Uses httpx.AsyncClient with the ASGITransport shipped in httpx 0.28+.


class _SlowSSEStream(httpx.AsyncByteStream):
    """Emit chunks with a small delay between them so a client that
    ``aclose()``s the response mid-stream actually cancels while the
    upstream is still producing.
    """

    def __init__(self, chunks: list[bytes], per_chunk_delay: float = 0.05) -> None:
        self._chunks = chunks
        self._delay = per_chunk_delay
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        import asyncio as _asyncio
        for chunk in self._chunks:
            await _asyncio.sleep(self._delay)
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


class _RaisingSSEStream(httpx.AsyncByteStream):
    """Emit N chunks then raise ``httpx.ReadTimeout`` to simulate an
    upstream that hangs after starting the stream.
    """

    def __init__(self, chunks: list[bytes], raise_after: int = 1) -> None:
        self._chunks = chunks
        self._raise_after = raise_after
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for i, chunk in enumerate(self._chunks):
            if i >= self._raise_after:
                raise httpx.ReadTimeout("simulated upstream timeout mid-stream")
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


_CANNED_NON_STREAM = {
    "id": "chatcmpl-stub-followup",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4o",
    "choices": [{
        "index": 0,
        "message": {"role": "assistant", "content": "pong"},
        "finish_reason": "stop",
    }],
    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
}


@pytest.fixture()
def stub_slow_streaming_transport(monkeypatch: pytest.MonkeyPatch):
    """Slow stream for stream=True; canned OpenAI dict for stream=False.

    Same file has two follow-up requests (non-streaming) after the
    cancel/timeout event — those need a successful non-streaming
    execute, or the admission-release probe becomes a wash on a real
    upstream error rather than a real admission leak.
    """
    async def _fake_execute(self, *, target, operation, payload,
                            credential_resolver, stream=False,
                            client_headers=None):
        if not stream:
            return dict(_CANNED_NON_STREAM)
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_SlowSSEStream(list(_SSE_CHUNKS), per_chunk_delay=0.1),
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


@pytest.fixture()
def stub_timeout_streaming_transport(monkeypatch: pytest.MonkeyPatch):
    """Raising stream for stream=True; canned OpenAI dict for stream=False.

    See ``stub_slow_streaming_transport`` for why the non-streaming
    path also needs to succeed.
    """
    async def _fake_execute(self, *, target, operation, payload,
                            credential_resolver, stream=False,
                            client_headers=None):
        if not stream:
            return dict(_CANNED_NON_STREAM)
        response = httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_RaisingSSEStream(list(_SSE_CHUNKS), raise_after=1),
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


@pytest.mark.asyncio
async def test_client_disconnect_midstream_releases_admission(
    seeded_profile, gateway_app, stub_slow_streaming_transport, it_db,
) -> None:
    """A client that abandons the stream mid-flight MUST NOT leak an
    admission slot. The stream's ``on_close`` hook is the release seam;
    if disconnect skips it, workspace inflight counters ratchet up
    forever and eventually every request refuses.
    """
    transport = httpx.ASGITransport(app=gateway_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://it-test",
    ) as ac:
        async with ac.stream(
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
            assert resp.status_code == 200
            # Read only the first chunk, then abandon by exiting the
            # context. Slow stream fixture ensures more chunks are still
            # pending upstream when we close, so this really cancels.
            async for _first in resp.aiter_raw():
                break

        # Fire a non-streaming follow-up. If admission wasn't released
        # when we bailed, this either 429s or hangs. Doing it inside
        # the same client to reuse the connection pool.
        followup = await ac.post(
            "/gateway/v1/completions",
            headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
            json={
                "profile": seeded_profile["profile_identifier"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
        )
    assert followup.status_code == 200, (
        f"follow-up after client disconnect returned "
        f"{followup.status_code} — admission slot leaked on disconnect"
    )


@pytest.mark.asyncio
async def test_upstream_timeout_midstream_finalizes_and_releases(
    seeded_profile, gateway_app, stub_timeout_streaming_transport, it_db,
) -> None:
    """When upstream stops sending bytes mid-stream (simulated by
    ``httpx.ReadTimeout``), the stream on_close hook must still fire so
    admission releases and the run doesn't wedge. The client sees a
    truncated body — an audit row should still land so ops can see
    what happened.
    """
    # Fire the failing stream through its OWN client — httpx's connection
    # pool holds broken-transport state after the ReadTimeout that
    # otherwise leaks into subsequent requests on the same client.
    # A fresh client for the follow-up isolates the admission-release
    # invariant from the client-side pool cleanup.
    transport1 = httpx.ASGITransport(app=gateway_app)
    async with httpx.AsyncClient(
        transport=transport1, base_url="http://it-test",
    ) as ac1:
        try:
            async with ac1.stream(
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
                assert resp.status_code == 200
                try:
                    async for _ in resp.aiter_raw():
                        pass
                except BaseException:  # noqa: BLE001
                    pass
        except BaseException:  # noqa: BLE001
            pass

    # Fresh client + fresh transport for the admission-release probe.
    # A leaked slot on the timeout path is a much nastier bug in
    # production than a leaked slot on client disconnect, because
    # timeouts happen every day even without misbehaving clients.
    transport2 = httpx.ASGITransport(app=gateway_app)
    async with httpx.AsyncClient(
        transport=transport2, base_url="http://it-test",
    ) as ac2:
        followup = await ac2.post(
            "/gateway/v1/completions",
            headers={"Authorization": f"Bearer {seeded_profile['agent_token']}"},
            json={
                "profile": seeded_profile["profile_identifier"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
        )
    assert followup.status_code == 200, (
        f"follow-up after upstream timeout returned "
        f"{followup.status_code} — admission slot leaked on timeout"
    )


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
