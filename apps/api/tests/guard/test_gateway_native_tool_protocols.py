from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.modules.guard.tools_native_stream_gate import wrap_native_tool_stream
from app.modules.guard.tools_stream_gate import StreamGateOutcome, StreamGateStatus
from app.modules.guard.tools_validator import scan_response_tool_calls
from app.modules.guard.tools_anthropic_converter import anthropic_stream_to_canonical
from app.runtime.accounting.normalizers.sse import parse_all


PII = "person@example.com"


def events(operation, *, custom=False):
    args = json.dumps({"email": PII})
    if operation == "anthropic_messages":
        return [
            {"type": "message_start", "message": {"id": "msg_test", "model": "claude-test", "usage": {"input_tokens": 5, "cache_read_input_tokens": 3}}},
            {"type": "content_block_start", "index": 0, "content_block": {"type": "tool_use", "id": "call_test", "name": "lookup", "input": {}}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": args[:10]}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": args[10:]}},
            {"type": "content_block_stop", "index": 0},
            {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 2}},
            {"type": "message_stop"},
        ]
    kind, field, prefix = ("custom_tool_call", "input", "response.custom_tool_call_input") if custom else ("function_call", "arguments", "response.function_call_arguments")
    argument = PII if custom else args
    item = {"type": kind, "id": "item_test", "call_id": "call_test", "name": "lookup", field: argument}
    return [
        {"type": "response.output_item.added", "output_index": 0, "item": {**item, field: ""}},
        {"type": prefix + ".delta", "output_index": 0, "item_id": "item_test", "delta": argument[:10]},
        {"type": prefix + ".delta", "output_index": 0, "item_id": "item_test", "delta": argument[10:]},
        {"type": prefix + ".done", "output_index": 0, "item_id": "item_test", field: argument},
        {"type": "response.output_item.done", "output_index": 0, "item": item},
        {"type": "response.completed", "response": {"output": [item], "usage": {"input_tokens": 5, "output_tokens": 2}}},
    ]


async def source(records):
    # CRLF and arbitrary byte boundaries must not bypass argument validation.
    data = b"".join((f"event: {record['type']}\r\ndata: {json.dumps(record)}\r\n\r\n").encode() for record in records)
    for i in range(0, len(data), 7):
        yield data[i:i + 7]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation,custom", [("anthropic_messages", False), ("openai_responses", False), ("openai_responses", True)])
async def test_native_stream_redacts_every_argument_copy(operation, custom):
    outcome = StreamGateOutcome()
    policy = AsyncMock(return_value=(True, None))
    data = b"".join([chunk async for chunk in wrap_native_tool_stream(source(events(operation, custom=custom)), operation=operation, outcome=outcome, policy_check=policy)])
    assert PII.encode() not in data
    assert b"lookup" in data
    assert b"usage" in data
    assert outcome.status == StreamGateStatus.OK
    assert outcome.correlation_ids
    policy.assert_awaited_once()
    assert PII not in json.dumps(policy.await_args.args)
    assert parse_all(data)[-1].event in {"message_stop", "response.completed"}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["anthropic_messages", "openai_responses"])
async def test_native_stream_policy_blocks_before_any_tool_bytes(operation):
    outcome = StreamGateOutcome()
    data = b"".join([chunk async for chunk in wrap_native_tool_stream(source(events(operation)), operation=operation, outcome=outcome, policy_check=AsyncMock(return_value=(False, "blocked-tool")))])
    assert b"lookup" not in data
    assert PII.encode() not in data
    assert b"error" in data
    assert outcome.status == StreamGateStatus.POLICY_BLOCK


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["anthropic_messages", "openai_responses"])
async def test_native_stream_interrupt_is_fail_closed(operation):
    outcome = StreamGateOutcome()
    data = b"".join([chunk async for chunk in wrap_native_tool_stream(source(events(operation)[:-1]), operation=operation, outcome=outcome)])
    assert b"lookup" not in data
    assert outcome.status == StreamGateStatus.VALIDATION_FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["omitted", "identity", "arguments", "event_identity", "duplicate"])
async def test_responses_final_snapshot_cannot_bypass_earlier_tool_validation(mutation):
    records = events("openai_responses")
    if mutation == "omitted":
        records[-1]["response"]["output"] = []
    elif mutation in {"identity", "arguments"}:
        item = records[-1]["response"]["output"][0]
        records[-1]["response"]["output"] = [{**item, "name" if mutation == "identity" else "arguments": "changed"}]
    elif mutation == "event_identity":
        records[1]["item_id"] = "other-item"
    else:
        records.insert(1, records[0])
    outcome = StreamGateOutcome()
    data = b"".join([chunk async for chunk in wrap_native_tool_stream(source(records), operation="openai_responses", outcome=outcome)])
    assert PII.encode() not in data
    assert b"lookup" not in data
    assert outcome.status == StreamGateStatus.VALIDATION_FAILED


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["duplicate", "not_tool", "not_closed", "bad_json"])
async def test_anthropic_malformed_tool_stream_is_fail_closed(mutation):
    records = events("anthropic_messages")
    if mutation == "duplicate":
        records.insert(4, {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}})
    elif mutation == "not_tool":
        records[1]["content_block"]["type"] = "text"
    elif mutation == "not_closed":
        records = [record for record in records if record["type"] != "content_block_stop"]
    else:
        records[3]["delta"]["partial_json"] = "broken-json"
    outcome = StreamGateOutcome()
    data = b"".join([chunk async for chunk in wrap_native_tool_stream(source(records), operation="anthropic_messages", outcome=outcome)])
    assert PII.encode() not in data
    assert b"lookup" not in data
    assert outcome.status == StreamGateStatus.VALIDATION_FAILED


@pytest.mark.parametrize("body", [
    {"content": [{"type": "tool_use", "id": "call_test", "name": "lookup", "input": {"email": PII}}]},
    {"output": [{"type": "function_call", "call_id": "call_test", "name": "lookup", "arguments": json.dumps({"email": PII})}]},
    {"output": [{"type": "custom_tool_call", "call_id": "call_test", "name": "lookup", "input": PII}]},
])
def test_nonstream_native_redaction_keeps_protocol_and_does_not_mutate(body):
    before = json.dumps(body)
    result = scan_response_tool_calls(body)
    assert result.error is None
    assert PII not in json.dumps(result.scanned_body)
    assert result.generated_calls == [{"name": "lookup", "id": "call_test"}]
    assert json.dumps(body) == before


@pytest.mark.asyncio
async def test_anthropic_canonical_stream_preserves_tools_cache_usage():
    data = b"".join([chunk async for chunk in anthropic_stream_to_canonical(source(events("anthropic_messages")))])
    records = [json.loads(event.data) for event in parse_all(data) if event.data != "[DONE]"]
    assert any(choice.get("delta", {}).get("tool_calls") for record in records for choice in record.get("choices", []))
    assert records[-1]["usage"]["prompt_tokens"] == 8
    assert records[-1]["usage"]["prompt_tokens_details"]["cached_tokens"] == 3
    assert records[-1]["usage"]["completion_tokens"] == 2


@pytest.mark.asyncio
async def test_anthropic_canonical_stream_interrupt_is_not_success():
    with pytest.raises(Exception, match="message_stop"):
        _ = [chunk async for chunk in anthropic_stream_to_canonical(source(events("anthropic_messages")[:-1]))]
