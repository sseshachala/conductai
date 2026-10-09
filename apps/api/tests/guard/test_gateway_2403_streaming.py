"""#2403 item 2 — a streaming request releases its admission slot exactly once.

One owner (the outermost stream wrapper) on every path: drained,
client disconnect, upstream error mid-stream.
"""
from __future__ import annotations

import httpx
import pytest

from tests.guard._gateway_handler_char_helpers import (  # noqa: F401 — gw is a fixture
    COND_MODEL, SSE_CHUNKS, drain, gw, ok_sse,
)

_BODY = {"model": COND_MODEL, "stream": True, "messages": [{"role": "user", "content": "hello"}]}


class _BrokenStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield SSE_CHUNKS[0]
        raise httpx.ReadError("upstream dropped")

    async def aclose(self):
        pass


def _broken_sse(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, request=request, headers={"content-type": "text/event-stream"},
                          stream=_BrokenStream())


@pytest.mark.asyncio
@pytest.mark.parametrize("durable", [True, False])
async def test_stream_drained_releases_once(gw, durable):
    gw.durable(durable)
    gw.upstream = [ok_sse]
    response, _ = await gw.call(dict(_BODY))
    assert gw.ticket.deferred is True and gw.ticket.release_calls == 0
    await drain(response)
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_client_disconnect_releases_once(gw):
    gw.upstream = [ok_sse]
    response, _ = await gw.call(dict(_BODY))
    iterator = response.body_iterator
    await iterator.__anext__()
    await iterator.aclose()  # client went away after the first chunk
    assert gw.ticket.release_calls == 1


@pytest.mark.asyncio
async def test_upstream_error_mid_stream_releases_once(gw):
    gw.upstream = [_broken_sse]
    response, _ = await gw.call(dict(_BODY))
    with pytest.raises(httpx.ReadError):
        await drain(response)
    assert gw.ticket.release_calls == 1
