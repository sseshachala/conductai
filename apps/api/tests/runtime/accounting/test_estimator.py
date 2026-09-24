"""Session 2 estimator self-checks. Covers every shape the consolidated
estimator absorbs from the two legacy implementations."""

from __future__ import annotations

from app.runtime.accounting.estimator import (
    ALL_SHAPES,
    InputShape,
    TokensEstimate,
    estimate_tokens,
)


def test_empty_body_returns_at_least_one_input_token():
    """Legacy behavior: max(1, ...) so ledger reserves something for an empty call."""
    result = estimate_tokens({})
    assert result.input_tokens == 1


def test_messages_string_content():
    body = {"messages": [{"role": "user", "content": "hello " * 100}]}
    result = estimate_tokens(body, include=frozenset([InputShape.MESSAGES]))
    assert result.input_tokens > 100
    assert result.breakdown[InputShape.MESSAGES.value] == result.input_tokens


def test_messages_list_content_extracts_text_parts():
    body = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "a" * 200},
                    {"type": "image_url", "image_url": {"url": "..."}},  # not text
                ],
            }
        ]
    }
    result = estimate_tokens(body, include=frozenset([InputShape.MESSAGES]))
    assert result.input_tokens == 200 // 4  # 50


def test_system_and_instructions_included_only_when_requested():
    body = {"system": "s" * 400, "instructions": "i" * 400}
    minimal = estimate_tokens(body, include=frozenset([InputShape.MESSAGES]))
    full = estimate_tokens(
        body,
        include=frozenset([InputShape.MESSAGES, InputShape.SYSTEM, InputShape.INSTRUCTIONS]),
    )
    assert minimal.input_tokens == 1  # only default max(1, ...)
    assert full.input_tokens > minimal.input_tokens


def test_response_input_shape_openai_responses_api():
    body = {"input": [{"content": [{"type": "input_text", "text": "hi " * 80}]}]}
    result = estimate_tokens(body, include=frozenset([InputShape.RESPONSE_INPUT]))
    assert result.input_tokens > 10


def test_output_allowance_honors_max_tokens():
    assert estimate_tokens({"max_tokens": 12345}).output_tokens_allowance == 12345
    assert estimate_tokens({}).output_tokens_allowance == 4096


def test_output_allowance_ignores_non_positive_max_tokens():
    assert estimate_tokens({"max_tokens": 0}).output_tokens_allowance == 4096
    assert estimate_tokens({"max_tokens": -1}).output_tokens_allowance == 4096


def test_coverage_recorded_on_result():
    result = estimate_tokens(
        {"messages": [{"role": "user", "content": "x"}]},
        include=frozenset([InputShape.MESSAGES]),
    )
    assert result.coverage == frozenset([InputShape.MESSAGES])


def test_result_is_frozen_dataclass():
    import pytest
    from dataclasses import FrozenInstanceError

    result = estimate_tokens({})
    with pytest.raises(FrozenInstanceError):
        result.input_tokens = 999  # type: ignore[misc]


def test_full_shape_coverage_greater_than_messages_only():
    """Documents the drift the two legacy estimators had — the shared estimator
    can be asked for full coverage OR minimal, and old callers pick minimal
    to preserve current behavior."""
    body = {
        "messages": [{"role": "user", "content": "hi"}],
        "system": "sys " * 100,
        "instructions": "inst " * 100,
    }
    minimal = estimate_tokens(body, include=frozenset([InputShape.MESSAGES]))
    full = estimate_tokens(body, include=ALL_SHAPES)
    assert full.input_tokens > minimal.input_tokens


def test_non_dict_body_is_safe():
    """Legacy path swallowed AttributeError; the new estimator returns 1."""
    assert estimate_tokens(None).input_tokens == 1  # type: ignore[arg-type]
    assert estimate_tokens("not a dict").input_tokens == 1  # type: ignore[arg-type]
