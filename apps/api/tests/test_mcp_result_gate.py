"""Synthetic result fixtures; private-key fixture coverage is tracked separately."""

import asyncio
import json
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest

from app.runtime import mcp_result_gate as gate
from app.runtime.mcp_credentials import McpRegistration
from app.runtime.mcp_governance import MCPGovernanceDenied, response_mode, transition


def registration(mode="block", transport="http"):
    return McpRegistration(
        str(uuid4()),
        str(uuid4()),
        "https://example.invalid/mcp",
        transport,
        None,
        {"state": "approved", "revision": 2, "response_mode": mode},
    )


def result(text="hello"):
    return {"content": [{"type": "text", "text": text}]}


def allow(_):
    return {"action": "ALLOW"}


@pytest.mark.parametrize("mode", ["audit", "block", "redact"])
def test_benign_results_unchanged(mode):
    original = result('{ "hello": "world" }')
    value, metadata = gate.inspect_result(original, mode, allow)
    assert value == original
    assert metadata["decision"] == ("audited" if mode == "audit" else "allowed")


@pytest.mark.parametrize("mode", ["audit", "block", "redact"])
def test_sensitive_key_context(mode):
    original = {"structuredContent": {"password": "synthetic-value"}}
    if mode == "block":
        with pytest.raises(gate.ResultDenied, match="secret_detected"):
            gate.inspect_result(original, mode, allow)
    else:
        value, metadata = gate.inspect_result(original, mode, allow)
        assert metadata["finding_types"]
        assert "synthetic-value" not in json.dumps(metadata)
        assert (value == original) == (mode == "audit")
        if mode == "redact":
            assert "synthetic-value" not in json.dumps(value)


def test_json_inside_text_is_inspected():
    value, metadata = gate.inspect_result(
        result(json.dumps({"password": "synthetic-value"})), "redact", allow
    )
    assert "synthetic-value" not in json.dumps(value)
    assert json.loads(value["content"][0]["text"])["password"].startswith("[REDACTED")
    assert metadata["decision"] == "redacted"


@pytest.mark.parametrize("action", ["BLOCK", "APPROVAL"])
@pytest.mark.parametrize("mode", ["audit", "block", "redact"])
def test_response_rules(action, mode):
    evaluate = Mock(return_value={"action": action})
    if mode == "audit":
        assert gate.inspect_result(result(), mode, evaluate)[0] == result()
    else:
        with pytest.raises(gate.ResultDenied, match="response_policy"):
            gate.inspect_result(result(), mode, evaluate)
    assert "hello" in evaluate.call_args.args[0]


@pytest.mark.parametrize(
    "decision", [None, {}, {"action": "ALLOW", "rule_id": "guard.engine_error"}]
)
def test_engine_failure_never_returns_content(decision):
    with pytest.raises(gate.ResultDenied, match="policy_unavailable"):
        gate.inspect_result(result(), "audit", lambda _: decision)


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"content": "text"},
        {"content": [{"type": "image"}]},
        {"structuredContent": []},
        {"content": [{"type": "text", "text": 1}]},
    ],
)
def test_unsupported_content(value):
    with pytest.raises(gate.ResultDenied, match="unsupported_content"):
        gate.inspect_result(value, "audit", allow)


def test_size_and_structure_bounds(monkeypatch):
    monkeypatch.setattr(gate, "MAX_BYTES", 10)
    with pytest.raises(gate.ResultDenied, match="size_limit"):
        gate.inspect_result(result("x" * 11), "block", allow)
    monkeypatch.setattr(gate, "MAX_BYTES", 1000)
    monkeypatch.setattr(gate, "MAX_DEPTH", 2)
    with pytest.raises(gate.ResultDenied, match="structure_limit"):
        gate.inspect_result(result(), "block", allow)
    monkeypatch.setattr(gate, "MAX_DEPTH", 32)
    monkeypatch.setattr(gate, "MAX_NODES", 2)
    with pytest.raises(gate.ResultDenied, match="structure_limit"):
        gate.inspect_result(result(), "block", allow)


class Body(httpx.AsyncByteStream):
    def __init__(self, value):
        self.value = value
        self.closed = False

    async def __aiter__(self):
        for offset in range(0, len(self.value), 7):
            yield self.value[offset : offset + 7]

    async def aclose(self):
        self.closed = True


@pytest.mark.parametrize(
    "case",
    [
        "ok",
        "sse",
        "encoding",
        "oversize",
        "invalid",
        "duplicate",
        "wrong_id",
        "error",
        "redirect",
    ],
)
def test_bounded_transport_no_retry_or_fallback(monkeypatch, case):
    calls = []
    streams = []

    def handler(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert payload["method"] == "tools/call"
        envelope = {"jsonrpc": "2.0", "id": payload["id"], "result": result()}
        if case == "wrong_id":
            envelope["id"] = "wrong"
        if case == "error":
            envelope["error"] = {"message": "untrusted detail"}
        raw = json.dumps(envelope).encode()
        if case == "oversize":
            monkeypatch.setattr(gate, "MAX_BYTES", 8)
        if case == "invalid":
            raw = b"not json"
        if case == "duplicate":
            raw = b'{"id":1,"id":2}'
        stream = Body(raw)
        streams.append(stream)
        return httpx.Response(
            302 if case == "redirect" else 200,
            stream=stream,
            headers={
                "content-type": "text/event-stream"
                if case == "sse"
                else "application/json",
                "content-encoding": "gzip" if case == "encoding" else "identity",
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        gate.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(handler), **kw),
    )
    if case == "ok":
        assert asyncio.run(gate._receive(registration(), "read", {})) == result()
    else:
        with pytest.raises(gate.ResultDenied) as exc:
            asyncio.run(gate._receive(registration(), "read", {}))
        assert "untrusted detail" not in str(exc.value)
    assert len(calls) == 1
    assert streams[0].closed


def test_sse_rejected_without_dispatch():
    with pytest.raises(gate.ResultDenied, match="unsupported_transport"):
        asyncio.run(gate._receive(registration(transport="sse"), "read", {}))


@pytest.mark.parametrize(
    "failure", [None, "upstream", "policy", "audit", "revocation", "predispatch"]
)
def test_release_requires_inspection_and_audit(monkeypatch, failure):
    from app.guard import policy

    calls = []

    async def receive(*_):
        calls.append("network")
        if failure == "upstream":
            raise TimeoutError("untrusted detail")
        return result('{"ok": true}')

    def record(_, metadata, *, check_current):
        calls.append(metadata["decision"])
        if failure == "predispatch" or (
            metadata["decision"] == "allowed" and failure == "audit"
        ):
            raise ConnectionError("database detail")
        if metadata["decision"] == "allowed" and failure == "revocation":
            raise gate.ResultDenied("registration_changed")

    evaluate = Mock(return_value={"action": "ALLOW"})
    if failure == "policy":
        evaluate.side_effect = RuntimeError("policy detail")
    monkeypatch.setattr(gate, "_receive", receive)
    monkeypatch.setattr(gate, "_record", record)
    monkeypatch.setattr(policy, "evaluate", evaluate)
    if failure:
        with pytest.raises(gate.ResultDenied) as exc:
            gate.call_inspected(registration(), "read", {})
        assert "detail" not in str(exc.value)
        assert calls[-1] == "withheld"
    else:
        assert gate.call_inspected(registration(), "read", {}) == {"ok": True}
        assert calls == ["dispatching", "network", "allowed"]
        assert evaluate.call_args.kwargs == {
            "gate": "response",
            "tool_names_supplied": ["read"],
        }
    assert calls.count("network") == (0 if failure == "predispatch" else 1)


def test_off_keeps_existing_client(monkeypatch):
    call = Mock(return_value="unchanged")
    monkeypatch.setattr("app.runtime.integrations.mcp_client.call_tool", call)
    assert registration("off").call_tool("read", {}) == "unchanged"
    call.assert_called_once()


def test_response_policy_survives_restore_and_validates_mode():
    current = transition(
        {"state": "approved", "revision": 2}, "response_policy", mode="block"
    )
    assert (
        response_mode(transition(transition(current, "quarantine"), "restore"))
        == "block"
    )
    with pytest.raises(MCPGovernanceDenied):
        transition(current, "response_policy", mode="invalid")
    with pytest.raises(MCPGovernanceDenied):
        transition(None, "response_policy", mode="block")


def test_inspected_slack_never_falls_back_for_missing_token(monkeypatch):
    from app.runtime.blocks.output_block import _resolve_slack_mcp

    item = registration()
    monkeypatch.setattr("app.core.database.get_db", lambda: iter([Mock()]))
    monkeypatch.setattr(
        "app.runtime.mcp_credentials.resolve_mcp_registration", lambda **_: item
    )
    assert _resolve_slack_mcp(item.workspace_id) is item
