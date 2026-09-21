"""Unit tests for tools_validator — Conduct's tool-calling contract.

These tests exist so the validator + redactor can be reviewed in
isolation from the shim wire-in. The shim (PR 1) and response gate
(PR 2 of epic #2159) both consume this module, so any drift in the
contract shows up here first.
"""
from __future__ import annotations

import json

import pytest

from app.modules.guard.tools_validator import (
    RedactionFailure,
    ValidationFailure,
    estimate_tools_tokens,
    redact_tool_arguments_json,
    redact_tool_parameters_schema,
    redact_tool_result_content,
    validate_messages,
    validate_tool_choice,
    validate_tools,
)


# ─── tool_choice ────────────────────────────────────────────────────


class TestValidateToolChoice:
    def test_none_is_ok(self) -> None:
        validate_tool_choice(None, [])
        validate_tool_choice(None, None)

    @pytest.mark.parametrize("mode", ["auto", "none", "required"])
    def test_supported_string_modes_pass(self, mode: str) -> None:
        validate_tool_choice(mode, None)

    @pytest.mark.parametrize("mode", ["Auto", "AUTO", "", "yes", "any", "true"])
    def test_unsupported_string_modes_rejected(self, mode: str) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice(mode, None)
        assert e.value.field == "tool_choice"
        assert "unsupported mode" in e.value.reason

    @pytest.mark.parametrize("bad", [1, 1.5, True, [], ("auto",)])
    def test_non_string_non_dict_rejected(self, bad) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice(bad, None)
        assert e.value.field == "tool_choice"

    def test_named_choice_matches_declared_tool(self) -> None:
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        validate_tool_choice(
            {"type": "function", "function": {"name": "get_weather"}}, tools,
        )

    def test_named_choice_missing_from_tools_rejected(self) -> None:
        tools = [{"type": "function", "function": {"name": "get_weather"}}]
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice(
                {"type": "function", "function": {"name": "send_email"}}, tools,
            )
        assert e.value.field == "tool_choice.function.name"
        assert "does not appear" in e.value.reason

    def test_named_choice_with_no_tools_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice(
                {"type": "function", "function": {"name": "x"}}, None,
            )
        assert e.value.field == "tool_choice.function.name"

    @pytest.mark.parametrize("bad_type", ["tool", "any", "function_call", None])
    def test_bad_type_rejected(self, bad_type) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice({"type": bad_type, "function": {"name": "x"}}, None)
        assert e.value.field == "tool_choice.type"

    def test_missing_function_object_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice({"type": "function"}, None)
        assert e.value.field == "tool_choice.function"

    def test_empty_function_name_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tool_choice({"type": "function", "function": {"name": ""}}, None)
        assert e.value.field == "tool_choice.function.name"


# ─── tools list ─────────────────────────────────────────────────────


class TestValidateTools:
    def test_valid_single_tool(self) -> None:
        validate_tools([{"type": "function", "function": {"name": "get_weather"}}])

    def test_valid_multiple_tools(self) -> None:
        validate_tools([
            {"type": "function", "function": {"name": "a"}},
            {"type": "function", "function": {"name": "b"}},
            {"type": "function", "function": {"name": "c"}},
        ])

    def test_non_list_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tools({"foo": "bar"})
        assert e.value.field == "tools"

    def test_empty_list_rejected(self) -> None:
        # An empty list is a caller mistake — omit the field instead.
        with pytest.raises(ValidationFailure):
            validate_tools([])

    def test_duplicate_names_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tools([
                {"type": "function", "function": {"name": "search"}},
                {"type": "function", "function": {"name": "search"}},
            ])
        assert e.value.field == "tools[1].function.name"
        assert "duplicate" in e.value.reason

    def test_non_function_type_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tools([{"type": "code_interpreter"}])
        assert e.value.field == "tools[0].type"

    def test_missing_function_name_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tools([{"type": "function", "function": {"description": "x"}}])
        assert e.value.field == "tools[0].function.name"

    def test_empty_function_name_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_tools([{"type": "function", "function": {"name": ""}}])
        assert e.value.field == "tools[0].function.name"


# ─── message structure ─────────────────────────────────────────────


class TestValidateMessages:
    def test_plain_conversation_ok(self) -> None:
        validate_messages([
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ])

    def test_tool_role_requires_tool_call_id(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_messages([
                {"role": "tool", "content": "result"},
            ])
        assert e.value.field == "messages[0].tool_call_id"

    def test_tool_role_empty_tool_call_id_rejected(self) -> None:
        with pytest.raises(ValidationFailure):
            validate_messages([{"role": "tool", "content": "r", "tool_call_id": ""}])

    def test_tool_role_with_valid_tool_call_id(self) -> None:
        validate_messages([
            {"role": "tool", "content": "42", "tool_call_id": "call_abc"},
        ])

    def test_assistant_null_content_needs_tool_calls(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_messages([{"role": "assistant", "content": None}])
        assert e.value.field == "messages[0].content"

    def test_assistant_null_content_with_tool_calls_ok(self) -> None:
        validate_messages([{
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": "call_1",
                "type": "function",
                "function": {"name": "get_weather", "arguments": "{}"},
            }],
        }])

    def test_assistant_null_content_with_empty_tool_calls_rejected(self) -> None:
        with pytest.raises(ValidationFailure):
            validate_messages([{
                "role": "assistant", "content": None, "tool_calls": [],
            }])

    def test_tool_call_missing_id_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_messages([{
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }],
            }])
        assert e.value.field.endswith(".id")

    def test_tool_call_missing_function_name_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_messages([{
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"arguments": "{}"},
                }],
            }])
        assert e.value.field.endswith(".function.name")

    def test_tool_call_non_function_type_rejected(self) -> None:
        with pytest.raises(ValidationFailure) as e:
            validate_messages([{
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "code",
                    "function": {"name": "x", "arguments": "{}"},
                }],
            }])
        assert e.value.field.endswith(".type")

    def test_tool_call_arguments_must_be_string(self) -> None:
        # OpenAI wire contract: arguments is a JSON-encoded string,
        # never a dict. Dict here means the caller wrote a non-portable
        # shape that upstream rejects inconsistently across providers.
        with pytest.raises(ValidationFailure) as e:
            validate_messages([{
                "role": "assistant", "content": None,
                "tool_calls": [{
                    "id": "call_1", "type": "function",
                    "function": {"name": "x", "arguments": {"a": 1}},
                }],
            }])
        assert e.value.field.endswith(".function.arguments")


# ─── redaction — arguments JSON ────────────────────────────────────


class TestRedactToolArgumentsJson:
    def test_no_secrets_roundtrips(self) -> None:
        args = '{"city":"San Francisco","units":"metric"}'
        out, found = redact_tool_arguments_json(args, source="req.tool_calls[0]")
        assert json.loads(out) == {"city": "San Francisco", "units": "metric"}
        assert found == []

    def test_empty_string_ok(self) -> None:
        out, found = redact_tool_arguments_json("", source="s")
        assert out == ""
        assert found == []

    def test_preserves_non_string_types(self) -> None:
        # Reviewer's guidance: preserve keys and non-string types.
        # Bool / int / float / null must round-trip untouched.
        args = json.dumps({
            "temperature": 0.7,
            "n": 3,
            "stream": True,
            "extra": None,
            "tags": ["a", "b"],
        })
        out, found = redact_tool_arguments_json(args, source="s")
        parsed = json.loads(out)
        assert parsed["temperature"] == 0.7
        assert parsed["n"] == 3
        assert parsed["stream"] is True
        assert parsed["extra"] is None
        assert parsed["tags"] == ["a", "b"]

    def test_invalid_json_raises_redaction_failure(self) -> None:
        # This is the "escaped secret" reviewer note: scanning encoded
        # strings can produce broken JSON. Instead we parse — and if
        # parse fails, block.
        with pytest.raises(RedactionFailure) as e:
            redact_tool_arguments_json('{"not:valid', source="s")
        assert e.value.source == "s"
        assert "not valid JSON" in e.value.reason

    def test_non_string_input_raises(self) -> None:
        with pytest.raises(RedactionFailure) as e:
            redact_tool_arguments_json({"a": 1}, source="s")  # type: ignore[arg-type]
        assert "JSON-encoded string" in e.value.reason

    def test_nested_structures_walked(self) -> None:
        args = json.dumps({
            "level1": {
                "level2": {
                    "value": "plain text",
                    "arr": ["a", "b", 1, 2],
                }
            }
        })
        out, _ = redact_tool_arguments_json(args, source="s")
        parsed = json.loads(out)
        assert parsed["level1"]["level2"]["value"] == "plain text"
        assert parsed["level1"]["level2"]["arr"] == ["a", "b", 1, 2]


# ─── redaction — parameters JSON Schema ────────────────────────────


class TestRedactToolParametersSchema:
    def test_none_is_ok(self) -> None:
        out, found = redact_tool_parameters_schema(None, source="s")
        assert out is None
        assert found == []

    def test_simple_schema_roundtrips(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city name"},
            },
        }
        out, _ = redact_tool_parameters_schema(schema, source="s")
        assert out == schema

    def test_walks_deep_string_leaves(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "x": {"description": "hello", "enum": ["a", "b"]},
            },
        }
        out, _ = redact_tool_parameters_schema(schema, source="s")
        assert out["properties"]["x"]["description"] == "hello"
        assert out["properties"]["x"]["enum"] == ["a", "b"]


# ─── redaction — tool_result content ───────────────────────────────


class TestRedactToolResultContent:
    def test_string_content_roundtrips(self) -> None:
        out, found = redact_tool_result_content("The weather is 72F")
        assert out == "The weather is 72F"
        assert found == []

    def test_empty_string_ok(self) -> None:
        out, found = redact_tool_result_content("")
        assert out == ""
        assert found == []

    def test_non_string_raises(self) -> None:
        with pytest.raises(RedactionFailure) as e:
            redact_tool_result_content({"result": 42})  # type: ignore[arg-type]
        assert e.value.source == "tool_result_content"


# ─── token estimation ─────────────────────────────────────────────


class TestEstimateToolsTokens:
    def test_empty_returns_zero(self) -> None:
        assert estimate_tools_tokens(None) == 0
        assert estimate_tools_tokens([]) == 0

    def test_scales_with_size(self) -> None:
        small = [{"type": "function", "function": {"name": "x"}}]
        big = [{
            "type": "function",
            "function": {
                "name": "x" * 100,
                "description": "d" * 500,
                "parameters": {"type": "object", "properties": {}},
            },
        }]
        assert estimate_tools_tokens(big) > estimate_tools_tokens(small)

    def test_conservative_upper_bound(self) -> None:
        # A single-word tool with a short description should still land
        # in the double-digit token range — not zero. Under-estimating
        # is the failure mode we're guarding against.
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Look up today's weather in a city.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string"},
                    },
                    "required": ["city"],
                },
            },
        }]
        est = estimate_tools_tokens(tools)
        assert est > 20, f"expected non-trivial estimate, got {est}"

    def test_non_serializable_returns_zero_gracefully(self) -> None:
        # Should never reach here (validator catches earlier), but the
        # helper must not crash the request path if it does.
        class _NotJson:
            pass
        assert estimate_tools_tokens([_NotJson()]) == 0



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
