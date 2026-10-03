"""Protocol-preserving response tool validation for Messages and Responses SSE.

Native tool streams are held until complete so neither partial arguments nor
the repeated final response snapshot can bypass validation. Chat streams use
the existing incremental gate. Accounting captures bytes before either gate.
"""
from __future__ import annotations

import json

from app.modules.guard.tools_stream_gate import StreamGateStatus
from app.modules.guard.tools_validator import scan_response_tool_calls, generate_tool_call_correlation_ids
from app.runtime.accounting.normalizers.sse import SSEParser


def _encode(event: str, data: dict) -> bytes:
    return (f"event: {event}\ndata: {json.dumps(data)}\n\n").encode()


async def wrap_native_tool_stream(upstream, *, operation, outcome, policy_check=None):
    parser = SSEParser()
    events = []
    blocks = {}
    argument_indexes = set()
    closed_blocks = set()
    size = 0
    anthropic = operation == "anthropic_messages"
    terminal = False

    def error(reason):
        outcome.status = StreamGateStatus.VALIDATION_FAILED
        outcome.reason = reason
        return _encode("error", {"type": "error", "error": {
            "type": "conduct_gateway_tool_arguments_validation_failed",
            "message": "Tool response refused by Conduct.",
        }})

    try:
        async for chunk in upstream:
            chunk = chunk.encode() if isinstance(chunk, str) else chunk
            size += len(chunk)
            if size > 8 * 1024 * 1024:
                yield error("tool stream exceeds validation buffer")
                return
            for event in parser.feed(chunk):
                data = json.loads(event.data)
                events.append((event.event, data))
                kind = data.get("type", event.event)
                if anthropic:
                    if kind == "content_block_start":
                        if data["index"] in blocks:
                            raise ValueError("duplicate content block")
                        blocks[data["index"]] = dict(data["content_block"])
                    elif kind == "content_block_delta" and data.get("delta", {}).get("type") == "input_json_delta":
                        block = blocks[data["index"]]
                        if block.get("type") not in {"tool_use", "server_tool_use"} or data["index"] in closed_blocks:
                            raise ValueError("unmatched tool argument delta")
                        block["_arguments"] = block.get("_arguments", "") + data["delta"]["partial_json"]
                    elif kind == "content_block_stop":
                        closed_blocks.add(data["index"])
                    terminal |= kind == "message_stop"
                else:
                    if kind == "response.output_item.added":
                        if data["output_index"] in blocks:
                            raise ValueError("duplicate output item")
                        blocks[data["output_index"]] = dict(data["item"])
                    elif kind in {"response.function_call_arguments.delta", "response.custom_tool_call_input.delta"}:
                        block = blocks[data["output_index"]]
                        field = "arguments" if "function_call" in kind else "input"
                        block[field] = block.get(field, "") + data["delta"]
                        argument_indexes.add(data["output_index"])
                    terminal |= kind == "response.completed"
        if not terminal:
            yield error("tool stream ended before completion")
            return
        if anthropic:
            for index, block in blocks.items():
                if block.get("type") in {"tool_use", "server_tool_use"} and index not in closed_blocks:
                    raise ValueError("tool block did not complete")
                if "_arguments" in block:
                    block["input"] = json.loads(block.pop("_arguments"))
            snapshot = {"content": list(blocks.values())}
        else:
            snapshot = next(data["response"] for _, data in reversed(events) if data.get("type") == "response.completed")
            # A final snapshot cannot discard or relabel earlier tool events.
            output = snapshot["output"]
            for index, block in blocks.items():
                if block.get("type") not in {"function_call", "custom_tool_call"}:
                    continue
                final = output[index]
                if any(block.get(key) != final.get(key) for key in ("type", "id", "call_id", "name")):
                    raise ValueError("tool identity changed before completion")
                field = "arguments" if block["type"] == "function_call" else "input"
                if (index in argument_indexes or block.get(field)) and block.get(field) != final.get(field):
                    raise ValueError("tool arguments changed before completion")
            for _, data in events:
                if data.get("type", "").startswith(("response.function_call_arguments.", "response.custom_tool_call_input.")):
                    index = data["output_index"]
                    final = output[index]
                    field = "arguments" if "function_call" in data["type"] else "input"
                    if index not in blocks or final.get("type") != ("function_call" if field == "arguments" else "custom_tool_call"):
                        raise ValueError("unmatched tool argument event")
                    if data.get("item_id") and data["item_id"] != final.get("id"):
                        raise ValueError("tool event identity changed")
        scanned = scan_response_tool_calls(snapshot)
        if scanned.error:
            yield error(scanned.error.reason)
            return
        items = scanned.scanned_body.get("content" if anthropic else "output", [])
        indexed = zip(blocks, items) if anthropic else enumerate(items)
        safe = {i: item for i, item in indexed if isinstance(item, dict) and item.get("type") in
                {"tool_use", "server_tool_use", "function_call", "custom_tool_call"}}
        calls = [{"id": item.get("call_id") or item.get("id"), "type": "function", "function": {
            "name": item.get("name", ""), "arguments": item.get("arguments") or json.dumps(item.get("input", {})),
        }} for item in safe.values()]
        if calls and policy_check:
            allowed, reason = await policy_check(calls)
            if not allowed:
                yield error(reason or "response_policy_block")
                outcome.status = StreamGateStatus.POLICY_BLOCK
                return
        outcome.correlation_ids.update(generate_tool_call_correlation_ids(scanned.generated_calls))
        emitted = set()
        for event, data in events:
            kind = data.get("type", event)
            index = data.get("index") if anthropic else data.get("output_index")
            item = safe.get(index)
            if anthropic and item:
                if kind == "content_block_start":
                    data["content_block"] = {**item, "input": {}}
                elif kind == "content_block_delta" and data.get("delta", {}).get("type") == "input_json_delta":
                    continue
                elif kind == "content_block_stop":
                    yield _encode("content_block_delta", {"type": "content_block_delta", "index": index,
                                                          "delta": {"type": "input_json_delta", "partial_json": json.dumps(item["input"])}})
            elif not anthropic and item:
                field = "arguments" if item["type"] == "function_call" else "input"
                if kind == "response.output_item.added":
                    data["item"] = {**item, field: ""}
                elif kind.endswith(".delta"):
                    if index in emitted:
                        continue
                    data["delta"] = item[field]
                    emitted.add(index)
                elif kind.endswith(".done"):
                    if kind == "response.output_item.done":
                        data["item"] = item
                    else:
                        data[field] = item[field]
            if kind == "response.completed":
                data["response"] = scanned.scanned_body
            yield _encode(event, data)
    except Exception:
        yield error("native tool stream validation failed")
    finally:
        close = getattr(upstream, "aclose", None)
        if close:
            await close()
