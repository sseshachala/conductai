"""Wire tests for the tool-call response-gate helper (#2159 PR 2).

Exercises ``apply_tool_call_gate`` — the seam between the executor's
response and the existing composed-engine response gate. Tests are
unit-level because ``handle_gateway_request`` proper needs Redis +
Vault + composed policy engine (integration-only); this helper is
pure enough to unit-test on its own.

Contract covered here:
  - Non-tool responses pass through with no routing_meta change.
  - Tool responses populate ``tool_calls_generated`` and substitute
    the response body with redacted arguments.
  - Malformed tool_call arguments produce a 502 with
    ``conduct_gateway_tool_arguments_validation_failed`` and mark
    ``response_gate_reason = validation_failure``.
  - Upstream cost is preserved: the 502 does NOT scrub upstream
    ``usage`` from the audit surface (audit lands the row from the
    successful upstream call; the 502 just replaces the client-facing
    envelope).
"""
from __future__ import annotations

import json

from fastapi.responses import JSONResponse

from app.modules.guard.gateway_handler import apply_tool_call_gate
from app.modules.guard.tools_validator import ResponseGateReason


def _resp(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


class TestApplyToolCallGate:
    def test_non_tool_response_pass_through(self) -> None:
        body = {
            "id": "x", "object": "chat.completion",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        }
        resp = _resp(body)
        out, meta = apply_tool_call_gate(
            resp, {}, workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        assert out.status_code == 200
        assert meta == {}
        # Body unchanged (no redaction needed on non-tool response).
        assert json.loads(out.body) == body

    def test_tool_response_populates_generated_calls(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "get_weather",
                                     "arguments": json.dumps({"city": "SF"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        resp = _resp(body)
        out, meta = apply_tool_call_gate(
            resp, None, workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        assert out.status_code == 200
        assert meta is not None
        assert meta["tool_calls_generated"] == [{"name": "get_weather", "id": "call_1"}]
        # Substituted body still has the tool_call with parseable args.
        out_body = json.loads(out.body)
        tc = out_body["choices"][0]["message"]["tool_calls"][0]
        assert tc["function"]["name"] == "get_weather"
        parsed_args = json.loads(tc["function"]["arguments"])
        assert parsed_args["city"] == "SF"

    def test_multiple_tool_calls_all_recorded(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": "call_a", "type": "function",
                         "function": {"name": "search", "arguments": "{}"}},
                        {"id": "call_b", "type": "function",
                         "function": {"name": "email",
                                      "arguments": json.dumps({"to": "x@y.com"})}},
                    ],
                },
                "finish_reason": "tool_calls",
            }],
        }
        _, meta = apply_tool_call_gate(
            _resp(body), None, workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        assert meta["tool_calls_generated"] == [
            {"name": "search", "id": "call_a"},
            {"name": "email", "id": "call_b"},
        ]

    def test_malformed_arguments_returns_502_validation_failure(self) -> None:
        # This is the terminal-block-not-scrub scenario. Upstream ran,
        # returned a tool_call whose arguments won't parse. Caller
        # must see 502 with the standardized error type; audit
        # response_gate_reason must be "validation_failure".
        body = {
            "id": "chatcmpl-bad",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "x", "arguments": '{"broken'},
                    }],
                },
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
        }
        out, meta = apply_tool_call_gate(
            _resp(body), {"pre": "existing"},
            workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        assert out.status_code == 502
        envelope = json.loads(out.body)
        assert envelope["error"]["type"] == "conduct_gateway_tool_arguments_validation_failed"
        assert envelope["error"]["gate"] == "response"
        assert "choices[0].message.tool_calls[0]" in envelope["error"]["source"]
        # Reason marker.
        assert meta["response_gate_reason"] == ResponseGateReason.VALIDATION_FAILURE
        assert meta["tool_calls_generated"] == []
        # Pre-existing routing_meta preserved (not clobbered).
        assert meta["pre"] == "existing"

    def test_unparseable_response_body_no_crash(self) -> None:
        # If upstream returned garbage bytes as JSONResponse (shouldn\'t
        # happen, but be defensive), the helper must not crash — it
        # treats the body as an empty dict and passes through.
        resp = JSONResponse(status_code=200, content={})
        resp.body = b"not-json"  # simulate malformed body cache
        out, meta = apply_tool_call_gate(
            resp, None, workspace_id="ws", provider="openai", model="gpt-4o",
        )
        assert out.status_code == 200
        assert meta is None

    def test_none_routing_meta_stays_none_when_no_tool_calls(self) -> None:
        # Passing routing_meta=None must not force allocation of a dict
        # on non-tool responses (avoids extra audit noise on
        # non-tool-using traffic).
        body = {"choices": [{"message": {"content": "hi"}}]}
        out, meta = apply_tool_call_gate(
            _resp(body), None, workspace_id="ws", provider="openai", model="gpt-4o",
        )
        assert meta is None


# --- correlation id wire tests (#2158) ---


class TestApplyToolCallGateCorrelation:
    def test_correlation_ids_populated_when_tool_calls_present(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "get_weather",
                                     "arguments": json.dumps({"city": "SF"})},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        out, meta = apply_tool_call_gate(
            _resp(body), None,
            workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        assert meta is not None
        # tool_call_correlation_ids populated alongside tool_calls_generated.
        assert "tool_call_correlation_ids" in meta
        assert set(meta["tool_call_correlation_ids"].keys()) == {"call_1"}
        # Correlation header present on the response with the same id.
        header = out.headers.get("x-conduct-tool-correlation-ids")
        assert header is not None
        assert header.startswith("call_1=")
        # And the correlation value matches what's in routing_meta.
        assert header == f"call_1={meta['tool_call_correlation_ids']['call_1']}"

    def test_no_correlation_header_when_no_tool_calls(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello"},
                "finish_reason": "stop",
            }],
        }
        out, meta = apply_tool_call_gate(
            _resp(body), None,
            workspace_id="ws-1", provider="openai", model="gpt-4o",
        )
        # Header must not be set (empty header is misleading).
        assert out.headers.get("x-conduct-tool-correlation-ids") is None
        assert meta is None

    def test_correlation_per_tool_call_multiple(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": "call_a", "type": "function",
                         "function": {"name": "s", "arguments": "{}"}},
                        {"id": "call_b", "type": "function",
                         "function": {"name": "e", "arguments": "{}"}},
                    ],
                },
                "finish_reason": "tool_calls",
            }],
        }
        out, meta = apply_tool_call_gate(
            _resp(body), None,
            workspace_id="ws", provider="openai", model="gpt-4o",
        )
        corrs = meta["tool_call_correlation_ids"]
        assert set(corrs.keys()) == {"call_a", "call_b"}
        # Header contains both entries.
        header = out.headers["x-conduct-tool-correlation-ids"]
        parts = set(header.split(","))
        assert parts == {f"call_a={corrs['call_a']}", f"call_b={corrs['call_b']}"}
