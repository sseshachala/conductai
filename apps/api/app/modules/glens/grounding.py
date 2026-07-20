"""Non-blocking groundedness monitor for GLens answers.

Flags numeric claims in the LLM's prose that don't trace back to any tool
result returned in the same turn. Logs a warning, never rejects. Legitimate
model-computed aggregates (sums, percentages) may not appear verbatim in raw
payloads, so this is a monitoring signal only.
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_NUMBER_RE = re.compile(r"[\$]?(\d[\d,]*(?:\.\d+)?)%?")
_MIN_MAGNITUDE = 10  # skip small integers — too noisy (list counts, dates)


def _extract_numbers(text: str) -> set[str]:
    numbers: set[str] = set()
    for m in _NUMBER_RE.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        try:
            value = float(raw)
        except ValueError:
            continue
        if abs(value) < _MIN_MAGNITUDE:
            continue
        normalized = str(int(value)) if value == int(value) else str(value)
        numbers.add(normalized)
    return numbers


def _flatten(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return str(value)


def find_ungrounded_numbers(answer: str, tool_results: list) -> list[str]:
    answer_numbers = _extract_numbers(answer)
    if not answer_numbers:
        return []
    source_text = " ".join(_flatten(r) for r in tool_results)
    return sorted(answer_numbers - _extract_numbers(source_text))


def check_grounded(answer: str, tool_results: list, *, skill: str | None = None) -> bool:
    if not tool_results:
        return True
    ungrounded = find_ungrounded_numbers(answer, tool_results)
    if ungrounded:
        log.warning("glens.grounding.ungrounded", skill=skill, numbers=ungrounded, answer=answer[:200])
    return True
