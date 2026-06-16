from __future__ import annotations

import json
from booster.crusher import crush, THRESHOLD, _try_json_array, _dedup_lines


def _big(text: str) -> str:
    """Pad text past threshold."""
    return text + " " * max(0, THRESHOLD - len(text) + 1)


def test_passthrough_below_threshold():
    text = "short text"
    result, orig, crushed = crush(text)
    assert result == text
    assert orig == crushed


def test_json_array_large_dropped():
    items = [{"id": i, "value": f"item-{i}", "label": f"label-{i}-extra"} for i in range(200)]
    text = json.dumps(items)
    result, orig, crushed = crush(text)
    assert crushed < orig
    assert "SmartCrusher" in result


def test_json_array_small_passthrough():
    items = [{"id": i} for i in range(5)]
    text = _big(json.dumps(items))
    result, orig, crushed = crush(text)
    # array too small to crush — may pass through or line-dedup
    # either way original meaning preserved
    assert "id" in result


def test_dedup_lines_collapses_repeats():
    line = "ERROR: connection refused"
    text = "\n".join([line] * 100)
    result, orig, crushed = crush(text)
    assert crushed < orig
    assert "omitted" in result


def test_dedup_lines_preserves_unique():
    lines = [f"line {i}" for i in range(30)]
    text = "\n".join(lines)
    result, orig, crushed = crush(text)
    # all unique — nothing to dedup, passthrough
    assert result == text


def test_never_returns_larger():
    text = "x\n" * 2000
    result, orig, crushed = crush(text)
    assert len(result.encode()) <= orig


def test_non_json_large_text_deduped():
    text = ("log line\n" * 500) + "final entry\n"
    result, orig, crushed = crush(text)
    assert crushed < orig
    assert "final entry" in result
