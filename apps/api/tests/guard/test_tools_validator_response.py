"""Unit tests for tools_validator — response-side helpers (PR 2 of epic
#2159) and tool-call correlation id helpers (#2158).

Split from ``test_tools_validator.py``.
"""
from __future__ import annotations

import json


# ─── response-side helpers (PR 2 additions) ────────────────────────


from app.modules.guard.tools_validator import (
    ResponseGateReason,
    extract_tool_results_supplied,
    extract_tools_offered,
    scan_response_tool_calls,
)


class TestScanResponseToolCalls:
    def test_body_without_tool_calls_passes_through(self) -> None:
        body = {
            "id": "x", "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "hi"}}],
        }
        r = scan_response_tool_calls(body)
        assert r.error is None
        assert r.generated_calls == []
        # No deep-copy needed when nothing to scan — helper returns same ref.
        assert r.scanned_body is body

    def test_empty_body_passes_through(self) -> None:
        r = scan_response_tool_calls({})
        assert r.error is None
        assert r.generated_calls == []

    def test_extracts_generated_tool_calls(self) -> None:
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": "call_1", "type": "function",
                         "function": {"name": "get_weather",
                                      "arguments": json.dumps({"city": "SF"})}},
                        {"id": "call_2", "type": "function",
                         "function": {"name": "send_email",
                                      "arguments": json.dumps({"to": "x@y.com"})}},
                    ],
                },
            }],
        }
        r = scan_response_tool_calls(body)
        assert r.error is None
        assert r.generated_calls == [
            {"name": "get_weather", "id": "call_1"},
            {"name": "send_email", "id": "call_2"},
        ]

    def test_redacts_arguments_in_place(self) -> None:
        # Arguments come back as valid JSON; scanner walks + re-serializes.
        # Value preservation of non-string types is enforced by the
        # underlying redact_tool_arguments_json (tested elsewhere) —
        # here we just confirm the wrapping call substitutes the
        # scanned body.
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "x",
                                     "arguments": json.dumps({"n": 3, "s": "hello"})},
                    }],
                },
            }],
        }
        r = scan_response_tool_calls(body)
        assert r.error is None
        assert r.scanned_body is not body   # deep-copied because tool_calls present
        # Non-string preserved.
        args = json.loads(r.scanned_body["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
        assert args["n"] == 3

    def test_malformed_arguments_json_returns_error(self) -> None:
        # This is the "block, don't scrub" scenario. Parse failure MUST
        # bubble up so caller emits 502 tool_arguments_validation_failed.
        body = {
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
        }
        r = scan_response_tool_calls(body)
        assert r.error is not None
        assert r.scanned_body is None
        assert "not valid JSON" in r.error.reason
        # Source path names the offending location for audit.
        assert "choices[0].message.tool_calls[0]" in r.error.source

    def test_no_arguments_still_records_generation(self) -> None:
        # A tool_call with no arguments is legal (no-arg function).
        # Audit should still record the {name, id}.
        body = {
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant", "content": None,
                    "tool_calls": [{
                        "id": "call_1", "type": "function",
                        "function": {"name": "ping", "arguments": ""},
                    }],
                },
            }],
        }
        r = scan_response_tool_calls(body)
        assert r.error is None
        assert r.generated_calls == [{"name": "ping", "id": "call_1"}]

    def test_non_dict_body_pass_through(self) -> None:
        r = scan_response_tool_calls("not a dict")  # type: ignore[arg-type]
        assert r.error is None
        assert r.generated_calls == []


class TestExtractToolsOffered:
    def test_none_returns_empty(self) -> None:
        assert extract_tools_offered({}) == []
        assert extract_tools_offered({"tools": None}) == []
        assert extract_tools_offered("not a dict") == []  # type: ignore[arg-type]

    def test_names_extracted(self) -> None:
        body = {
            "tools": [
                {"type": "function", "function": {"name": "a"}},
                {"type": "function", "function": {"name": "b"}},
            ],
        }
        assert extract_tools_offered(body) == ["a", "b"]

    def test_malformed_entries_skipped(self) -> None:
        body = {
            "tools": [
                {"type": "function", "function": {"name": "a"}},
                "not-a-dict",
                {"type": "function"},  # missing function
                {"type": "function", "function": {"name": ""}},  # empty name
                {"type": "function", "function": {"name": "b"}},
            ],
        }
        # Non-dict skipped; missing function skipped; empty-name accepted
        # here (extractor is best-effort; validator rejects earlier so
        # this path is theoretical, but audit should still land).
        result = extract_tools_offered(body)
        assert "a" in result and "b" in result


class TestExtractToolResultsSupplied:
    def test_no_tool_messages(self) -> None:
        body = {"messages": [{"role": "user", "content": "hi"}]}
        assert extract_tool_results_supplied(body) == []

    def test_tool_call_ids_extracted(self) -> None:
        body = {"messages": [
            {"role": "user", "content": "x"},
            {"role": "assistant", "content": "y"},
            {"role": "tool", "content": "42", "tool_call_id": "call_a"},
            {"role": "tool", "content": "7", "tool_call_id": "call_b"},
        ]}
        assert extract_tool_results_supplied(body) == ["call_a", "call_b"]

    def test_malformed_input_returns_empty(self) -> None:
        assert extract_tool_results_supplied({}) == []
        assert extract_tool_results_supplied({"messages": "not a list"}) == []
        assert extract_tool_results_supplied("not a dict") == []  # type: ignore[arg-type]


class TestResponseGateReason:
    def test_stable_string_values(self) -> None:
        # Audit tables + Flight Recorder queries hard-code these
        # strings; changing them silently would break dashboards.
        assert ResponseGateReason.POLICY_BLOCK == "policy_block"
        assert ResponseGateReason.VALIDATION_FAILURE == "validation_failure"


# --- correlation id helpers (#2158) ---


from app.modules.guard.tools_validator import (
    encode_correlation_header,
    generate_tool_call_correlation_ids,
    parse_correlation_header,
)


class TestGenerateToolCallCorrelationIds:
    def test_empty_returns_empty(self) -> None:
        assert generate_tool_call_correlation_ids([]) == {}
        assert generate_tool_call_correlation_ids(None) == {}  # type: ignore[arg-type]

    def test_one_id_per_tool_call(self) -> None:
        calls = [
            {"name": "a", "id": "call_1"},
            {"name": "b", "id": "call_2"},
        ]
        out = generate_tool_call_correlation_ids(calls)
        assert set(out.keys()) == {"call_1", "call_2"}
        assert len(set(out.values())) == 2

    def test_correlation_id_shape(self) -> None:
        # 16 hex chars sliced from uuid4.
        out = generate_tool_call_correlation_ids([{"name": "x", "id": "call_1"}])
        cid = out["call_1"]
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)

    def test_missing_id_skipped(self) -> None:
        # Defensive: if a call comes in without an id, don't allocate a
        # correlation for it (no way to join back to the audit).
        out = generate_tool_call_correlation_ids([{"name": "x"}])
        assert out == {}

    def test_correlations_distinct_across_calls(self) -> None:
        # Each helper call is its own correlation event, so retried
        # attempts get distinct correlations (intentional randomness).
        calls = [{"name": "x", "id": "call_1"}]
        out1 = generate_tool_call_correlation_ids(calls)
        out2 = generate_tool_call_correlation_ids(calls)
        assert set(out1.keys()) == set(out2.keys())
        assert out1["call_1"] != out2["call_1"]


class TestEncodeCorrelationHeader:
    def test_empty_returns_empty_string(self) -> None:
        # Caller must SKIP setting the header on empty (many servers
        # drop empty-valued headers).
        assert encode_correlation_header({}) == ""

    def test_single_entry(self) -> None:
        assert encode_correlation_header({"call_1": "corr_a"}) == "call_1=corr_a"

    def test_multiple_entries_comma_separated(self) -> None:
        out = encode_correlation_header({
            "call_1": "corr_a",
            "call_2": "corr_b",
        })
        parts = set(out.split(","))
        assert parts == {"call_1=corr_a", "call_2=corr_b"}


class TestParseCorrelationHeader:
    def test_missing_returns_empty(self) -> None:
        assert parse_correlation_header(None) == {}
        assert parse_correlation_header("") == {}

    def test_round_trip(self) -> None:
        original = {"call_1": "corr_a", "call_2": "corr_b"}
        header = encode_correlation_header(original)
        assert parse_correlation_header(header) == original

    def test_ignores_malformed_pairs(self) -> None:
        # Best-effort — drop noise, keep good pairs.
        assert parse_correlation_header("call_1=corr_a,garbage,=only_value,call_2=corr_b") == {
            "call_1": "corr_a",
            "call_2": "corr_b",
        }

    def test_drops_unsafe_tool_call_ids(self) -> None:
        # Symmetric with encode side — model-controlled ids that would
        # never be emitted are also refused on parse.
        assert parse_correlation_header("call\x00bad=corr_a,call_ok=corr_b") == {
            "call_ok": "corr_b",
        }

    def test_first_occurrence_wins(self) -> None:
        assert parse_correlation_header("call_1=first,call_1=second") == {"call_1": "first"}
