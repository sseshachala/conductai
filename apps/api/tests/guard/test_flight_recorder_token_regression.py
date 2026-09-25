"""Exercise token bindings in both Flight Recorder audit writers."""
import json
from unittest.mock import MagicMock

import pytest

from app.guard import audit


@pytest.mark.parametrize("writer", ["record", "finalize"])
@pytest.mark.parametrize("stream", [False, True])
@pytest.mark.parametrize("protocol", ["responses", "chat", "anthropic"])
def test_audit_writers_persist_provider_usage(monkeypatch, writer, stream, protocol):
    if protocol == "anthropic":
        provider, model, operation = "anthropic", "claude-sonnet-4-6", "anthropic_messages"
        usage = {"input_tokens": 100, "output_tokens": 50,
                 "cache_read_input_tokens": 20, "cache_creation_input_tokens": 10}
        expected_input = 130
        events = [
            {"type": "message_start", "message": {"usage": {**usage, "output_tokens": 0}}},
            {"type": "message_delta", "usage": {"output_tokens": 50}},
            {"type": "message_stop"},
        ]
    elif protocol == "responses":
        provider, model, operation = "openai", "gpt-4.1", "openai_responses"
        usage = {"input_tokens": 100, "output_tokens": 50}
        expected_input = 100
        events = [{"type": "response.completed", "response": {"usage": usage}}]
    else:
        provider, model, operation = "openai", "gpt-4.1", "openai_chat_completions"
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        expected_input = 100
        events = [{"usage": usage}]
    payload = json.dumps({"usage": usage}).encode()
    if stream:
        payload = b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)
        if protocol == "chat":
            payload += b"data: [DONE]\n\n"

    db = MagicMock()
    db.execute.return_value.rowcount = 1
    monkeypatch.setattr(audit, "SessionLocal", lambda: db)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *args: None)
    kwargs = dict(
        workspace_id="11111111-1111-1111-1111-111111111111",
        provider=provider, model=model, body={}, response_bytes=payload,
        routing_meta={"operation": operation}, decision="allowed",
        duration_ms=10, clerk_user_id="user_test", ai_tool="test",
    )
    if writer == "record":
        audit.record(**kwargs, rule_id=None)
    else:
        assert audit.finalize(**kwargs, row_id="22222222-2222-2222-2222-222222222222")
    params = next(
        call.args[1] for call in db.execute.call_args_list
        if "guard_audit_events" in str(call.args[0])
    )
    assert params["tin"] == expected_input
    assert params["tout"] == 50


def test_record_uses_route_without_routing_metadata(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(audit, "SessionLocal", lambda: db)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *args: None)
    audit.record(
        "11111111-1111-1111-1111-111111111111", "user_test", "test",
        "openai", "gpt-4.1", "allowed", None, 10,
        body={}, response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        route="/gateway/v1/openai/v1/responses",
    )
    params = db.execute.call_args.args[1]
    assert (params["tin"], params["tout"]) == (100, 50)
