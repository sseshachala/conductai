"""Groundedness check — flags numeric claims in a GLens answer that don't
trace back to any tool result returned in the same turn.

This is a best-effort, non-blocking safety net: GLens's contract is that the
model may only speak from tool output, never from parametric memory. Exact
math (percentages, rounding, sums the model computes itself) can legitimately
produce numbers that don't appear verbatim in the raw payload, so this check
logs a warning rather than rejecting the answer outright.
"""
from __future__ import annotations

import json
import re

import structlog

log = structlog.get_logger(__name__)

# Matches integers and decimals, including those with thousands separators
# or a leading currency symbol (e.g. "$1,240", "12", "3.5", "42%").
_NUMBER_RE = re.compile(r"[\$]?(\d[\d,]*(?:\.\d+)?)%?")

# Small integers are extremely common in prose (e.g. "a few", numbered lists,
# dates) and produce too many false positives to be worth checking.
_MIN_MAGNITUDE = 10


def _extract_numbers(text: str) -> set[str]:
    """Extract normalized numeric tokens (no commas, no trailing .0) from text."""
    numbers = set()
    for match in _NUMBER_RE.finditer(text or ""):
        raw = match.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if abs(value) < _MIN_MAGNITUDE:
            continue
        # Normalize "42.0" -> "42" so it matches an int rendered without decimals
        normalized = str(int(value)) if value == int(value) else str(value)
        numbers.add(normalized)
    return numbers


def _flatten_to_text(value) -> str:
    """Serialize a tool result (dict/list/primitive) to a single searchable string."""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def find_ungrounded_numbers(answer: str, tool_results: list) -> list[str]:
    """
    Return numeric tokens present in `answer` but absent from every tool
    result payload in `tool_results`. Empty list means the answer is grounded
    (or contains no checkable numeric claims).
    """
    answer_numbers = _extract_numbers(answer)
    if not answer_numbers:
        return []

    source_text = " ".join(_flatten_to_text(r) for r in tool_results)
    source_numbers = _extract_numbers(source_text)

    return sorted(answer_numbers - source_numbers)


def check_grounded(answer: str, tool_results: list, *, skill: str | None = None) -> bool:
    """
    Log a warning if `answer` contains numeric claims not traceable to any
    tool result. Always returns True (non-blocking) — the check is a
    monitoring signal, not a hard gate, since legitimate model-computed
    aggregates (percentages, sums) may not appear verbatim in raw payloads.
    """
    if not tool_results:
        return True

    ungrounded = find_ungrounded_numbers(answer, tool_results)
    if ungrounded:
        log.warning(
            "glens.grounding.ungrounded_numbers",
            skill=skill,
            numbers=ungrounded,
            answer=answer[:200],
        )
    return True
