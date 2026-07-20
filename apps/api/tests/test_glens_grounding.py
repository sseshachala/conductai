"""Unit tests for GLens's groundedness check (glens/grounding.py).

No DB, no LLM — pure function tests over the numeric-claim extraction logic.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

from app.modules.glens.grounding import check_grounded, find_ungrounded_numbers


def test_grounded_number_passes():
    tool_results = [{"events_today": 42, "blocked_today": 5}]
    ungrounded = find_ungrounded_numbers("You have 42 events today.", tool_results)
    assert ungrounded == []


def test_fabricated_number_is_flagged():
    tool_results = [{"events_today": 42}]
    ungrounded = find_ungrounded_numbers("You have 9999 events today.", tool_results)
    assert ungrounded == ["9999"]


def test_currency_and_percent_formatting_normalizes():
    tool_results = [{"total_cost_usd": 1240.5, "score": 87}]
    ungrounded = find_ungrounded_numbers("Spend was $1,240.50 and score is 87%.", tool_results)
    assert ungrounded == []


def test_small_numbers_are_ignored():
    """Small integers (list counts, dates) are too noisy to check reliably."""
    ungrounded = find_ungrounded_numbers("Here are 3 results from page 1.", [{"other": "data"}])
    assert ungrounded == []


def test_no_tool_results_short_circuits():
    """With no tool results at all, find_ungrounded_numbers still flags
    numeric claims (nothing to compare against); the non-blocking short
    circuit lives in check_grounded, tested separately below."""
    ungrounded = find_ungrounded_numbers("You have 9999 events today.", [])
    assert ungrounded == ["9999"]


def test_number_across_multiple_tool_results():
    tool_results = [{"a": 1}, {"blocked_today": 500}]
    ungrounded = find_ungrounded_numbers("500 events were blocked.", tool_results)
    assert ungrounded == []


def test_check_grounded_never_raises_and_returns_true():
    """check_grounded is a non-blocking monitoring signal — always returns True."""
    assert check_grounded("9999 events happened.", [{"events_today": 1}], skill="governance") is True
    assert check_grounded("42 events happened.", [{"events_today": 42}], skill="governance") is True
    assert check_grounded("", [], skill="governance") is True
