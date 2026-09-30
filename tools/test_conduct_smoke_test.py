"""Offline contract tests; no real credentials or network calls."""
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("smoke", Path(__file__).with_name("conduct_smoke_test.py"))
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.mark.parametrize("url", ["http://remote.example/v1", "https://user:password@example.test", "https://example.test/?secret=x"])
def test_unsafe_url(url):
    with pytest.raises(smoke.CheckFailed):
        smoke.endpoint(url)


def test_json_and_sse():
    value = {"jsonrpc": "2.0", "id": 1, "result": {}}
    raw = json.dumps(value).encode()
    assert smoke.decode(raw, "application/json") == value
    assert smoke.decode(b"event: message\ndata: " + raw + b"\n\n", "text/event-stream") == value


def test_redirect_refused():
    with pytest.raises(smoke.CheckFailed):
        smoke.NoRedirect().redirect_request(None, None, 302, "", {}, "https://other.test")


def test_mcp_requires_matching_response_and_explicit_verdict():
    client = Mock()
    client.post.return_value = (200, {"id": 1, "result": {"content": []}}, {})
    mcp = smoke.MCP(client, "https://api.example.test/mcp", "synthetic", "test")
    with pytest.raises(smoke.CheckFailed, match="no policy verdict"):
        mcp.check("guard_check", {}, "allow")
    client.post.return_value = (200, {"id": 99, "result": {}}, {})
    with pytest.raises(smoke.CheckFailed):
        mcp.call("tools/list", {})


@pytest.mark.parametrize("status,data,marker,passes", [
    (200, {"choices": [{"message": {"content": "hello"}}]}, None, True),
    (200, {}, None, False),
    (401, {"error": "rule-demo"}, "rule-demo", False),
    (403, {"error": "invalid token"}, "rule-demo", False),
    (400, {"error": "BLOCKED rule-demo"}, "rule-demo", True),
])
def test_inference_contract(status, data, marker, passes):
    client = Mock()
    client.post.return_value = (status, data, {})
    def check():
        smoke.inference(client, "http://localhost:4000/v1", "synthetic", "model", "hello", "test", marker)
    if passes:
        check()
    else:
        with pytest.raises(smoke.CheckFailed):
            check()


def test_default_run_skips_inference(tmp_path, monkeypatch, capsys):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api_url": "https://api.example.test", "agent_token": "synthetic-private"}))
    client = Mock()
    replies = [
        {"protocolVersion": "2024-11-05"}, {},
        {"tools": [{"name": "guard_check"}]},
        {"content": [{"type": "text", "text": "ok"}]},
        {"content": [{"type": "text", "text": "BLOCKED rule"}]},
    ]
    def post(url, token, body, headers):
        return 200, {"id": body.get("id"), "result": replies.pop(0)}, {}
    client.post.side_effect = post
    monkeypatch.setattr(smoke, "Client", lambda ca: client)
    assert smoke.main(["--config", str(config)]) == 0
    output = capsys.readouterr().out
    assert "PASS  MCP" in output
    assert "SKIP  Gateway" in output and "SKIP  LiteLLM" in output
    assert "synthetic-private" not in output
    assert client.post.call_count == 5


@pytest.mark.parametrize("status,body,accepted", [
    (503, {"error": "policy_transport_failed"}, True),
    (200, {"choices": [{"message": "hello"}], "error": "policy_transport_failed"}, False),
    (503, {"error": "provider unavailable"}, False),
    (401, {"error": "policy_transport_failed"}, False),
])
def test_fault_response_is_not_confused_with_provider_or_auth_failure(status, body, accepted):
    client = Mock()
    client.post.return_value = status, body, {}
    def check():
        smoke.inference(client, "http://localhost:4000/v1", "synthetic", "test", "hello", "run",
                        "policy_transport_failed", fault=True)
    if accepted:
        check()
    else:
        with pytest.raises(smoke.CheckFailed):
            check()
