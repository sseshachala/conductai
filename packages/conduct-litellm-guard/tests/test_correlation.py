"""Tool-call correlation IDs surfaced by the shim (#2168)."""
from __future__ import annotations

import pytest

from conduct_litellm_guard import ConductGuard
from conduct_litellm_guard.guardrail import parse_correlation_header


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _resp(headers):
    tc = _Obj(id="call_abc", function=_Obj(name="send_email"))
    r = _Obj(choices=[_Obj(message=_Obj(tool_calls=[tc]))])
    r._hidden_params = {"additional_headers": headers}
    return r


def test_parse_header_drops_malformed() -> None:
    assert parse_correlation_header("a=9c4f3e21a7b0d8e1,b,c=,d=zz") == {"a": "9c4f3e21a7b0d8e1"}
    assert parse_correlation_header(None) == {}


@pytest.mark.asyncio
async def test_post_call_hook_stashes_correlation_ids(caplog) -> None:
    g = ConductGuard.__new__(ConductGuard)
    data: dict = {}
    resp = _resp({"llm_provider-x-conduct-tool-correlation-ids": "call_abc=9c4f3e21a7b0d8e1,bad=zz"})
    with caplog.at_level("INFO"):
        out = await g.async_post_call_success_hook(data, None, resp)
    assert out is resp
    assert data["metadata"]["conduct_tool_correlation_ids"] == {"call_abc": "9c4f3e21a7b0d8e1"}
    assert "correlation_id=9c4f3e21a7b0d8e1" in caplog.text


@pytest.mark.asyncio
async def test_post_call_hook_no_header_is_noop() -> None:
    g = ConductGuard.__new__(ConductGuard)
    data: dict = {}
    resp = _resp({})
    assert await g.async_post_call_success_hook(data, None, resp) is resp
    assert "metadata" not in data
