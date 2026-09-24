"""Shadow-delta metrics self-checks (#2209 Session 6).

Verifies the aggregation logic used by Session 7's activation gate.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.runtime.accounting.metrics import compute_deltas_from_rows


@dataclass
class _R:
    calculated_cost_microdollars: int
    legacy_cost_microdollars: int


def test_empty_rows_produce_zero_deltas():
    d = compute_deltas_from_rows([])
    assert d == {
        "new_cost": 0,
        "legacy_cost": 0,
        "sum_abs_delta": 0,
        "max_abs_delta": 0,
    }


def test_matched_rows_produce_zero_delta():
    rows = [_R(100, 100), _R(200, 200), _R(300, 300)]
    d = compute_deltas_from_rows(rows)
    assert d["new_cost"] == 600
    assert d["legacy_cost"] == 600
    assert d["sum_abs_delta"] == 0
    assert d["max_abs_delta"] == 0


def test_positive_deltas_summed_by_absolute_value():
    """New cost above legacy on some rows, below on others — Σ|Δ| catches both."""
    rows = [_R(100, 80), _R(200, 250), _R(300, 300)]
    d = compute_deltas_from_rows(rows)
    assert d["sum_abs_delta"] == 20 + 50 + 0
    assert d["max_abs_delta"] == 50


def test_missing_legacy_treated_as_zero_delta_computed_against_new():
    """Attempts that had no legacy cost recorded (e.g. Session 4 hook fired
    without a cost path) show as a full delta against zero."""
    rows = [_R(100, 0), _R(200, 0)]
    d = compute_deltas_from_rows(rows)
    assert d["new_cost"] == 300
    assert d["legacy_cost"] == 0
    assert d["sum_abs_delta"] == 300
    assert d["max_abs_delta"] == 200


def test_none_values_treated_as_zero():
    rows = [
        type("R", (), {"calculated_cost_microdollars": None, "legacy_cost_microdollars": 100})(),
        type("R", (), {"calculated_cost_microdollars": 200, "legacy_cost_microdollars": None})(),
    ]
    d = compute_deltas_from_rows(rows)
    assert d["new_cost"] == 200
    assert d["legacy_cost"] == 100
    assert d["sum_abs_delta"] == 100 + 200
