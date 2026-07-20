"""Unit tests for GLens groundedness monitor (no DB, no LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.modules.glens.grounding import check_grounded, find_ungrounded_numbers


def test_grounded_number_passes():
    assert find_ungrounded_numbers("You have 42 events today.", [{"events_today": 42}]) == []


def test_fabricated_number_flagged():
    assert find_ungrounded_numbers("You have 9999 events.", [{"events_today": 42}]) == ["9999"]


def test_currency_and_percent_normalize():
    assert find_ungrounded_numbers("Spend $1,240.50 score 87%.", [{"total_cost_usd": 1240.5, "score": 87}]) == []


def test_small_numbers_ignored():
    assert find_ungrounded_numbers("Here are 3 results from page 1.", [{"other": "data"}]) == []


def test_multiple_tool_results():
    assert find_ungrounded_numbers("500 events blocked.", [{"a": 1}, {"blocked_today": 500}]) == []


def test_check_grounded_always_true():
    assert check_grounded("9999 events.", [{"events_today": 1}], skill="governance") is True
    assert check_grounded("", [], skill="governance") is True
