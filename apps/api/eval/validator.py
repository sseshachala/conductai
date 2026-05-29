"""
Minimum-bar validator for the Conduct Eval Harness.

The validator compares a freshly computed :class:`EvalReport` against committed
baselines in ``reports/baselines/`` and enforces a minimum quality bar.

Use it in CI to gate merges that would regress playbook quality:

    from eval.validator import validate_report, ValidationResult
    from eval.runner import run_all

    report = run_all()
    result = validate_report(report)
    if not result.passed:
        for alert in result.regression_alerts:
            print(f"REGRESSION: {alert['slug']} dropped {alert['delta']} pts")
        sys.exit(1)

Minimum bar rules
-----------------
  1. No playbook may drop below grade D (structural score < 60%).
  2. No playbook may regress by more than 5 structural points vs its baseline.
  3. Every playbook must have a test_trigger fixture (test_fixture_present criterion).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from eval.report import EvalReport
from eval.scorer import PlaybookScore


# Minimum passing grade threshold (inclusive).
# Playbooks scoring below this grade trigger a bar violation.
MIN_GRADE = "D"
_GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}

# Maximum allowed structural point regression vs baseline.
MAX_REGRESSION_PTS = 5


@dataclass
class ValidationResult:
    """Result of a minimum-bar validation check."""

    passed: bool
    """True if all checks pass."""

    below_bar: list[dict[str, Any]] = field(default_factory=list)
    """Playbooks that fell below the minimum grade bar."""

    regression_alerts: list[dict[str, Any]] = field(default_factory=list)
    """Playbooks that regressed significantly vs their baseline."""

    missing_fixture: list[str] = field(default_factory=list)
    """Playbooks missing the test_fixture_present criterion."""

    def summary(self) -> str:
        lines = ["Validation result: " + ("PASS" if self.passed else "FAIL")]
        if self.below_bar:
            lines.append(f"\nBelow min grade ({MIN_GRADE}):")
            for item in self.below_bar:
                lines.append(f"  {item['slug']}: grade {item['grade']} ({item['pct']:.1f}%)")
        if self.regression_alerts:
            lines.append("\nRegressions vs baseline:")
            for item in self.regression_alerts:
                lines.append(
                    f"  {item['slug']}: {item['before']} -> {item['after']} "
                    f"(delta {item['delta']:+d} pts)"
                )
        if self.missing_fixture:
            lines.append("\nMissing test fixture:")
            for slug in self.missing_fixture:
                lines.append(f"  {slug}")
        return "\n".join(lines)


def validate_report(
    report: EvalReport,
    baselines_dir: Path | None = None,
) -> ValidationResult:
    """
    Validate an :class:`EvalReport` against the minimum quality bar.

    Parameters
    ----------
    report:
        The freshly computed eval report to validate.
    baselines_dir:
        Override the default baselines directory (useful for tests).
    """
    from eval.benchmark import BASELINES_DIR, get_playbook_baseline

    _baselines_dir = baselines_dir or BASELINES_DIR

    below_bar: list[dict[str, Any]] = []
    regression_alerts: list[dict[str, Any]] = []
    missing_fixture: list[str] = []

    for score in report.scores:
        # Rule 1: minimum grade bar
        grade_rank = _GRADE_ORDER.get(score.grade, 4)
        min_rank = _GRADE_ORDER.get(MIN_GRADE, 3)
        if grade_rank > min_rank:
            below_bar.append({
                "slug": score.slug,
                "grade": score.grade,
                "pct": score.pct,
                "structural_score": score.structural_score,
            })

        # Rule 2: regression vs baseline
        baseline = get_playbook_baseline(score.slug)
        if baseline:
            base_playbooks = baseline.get("playbooks") or []
            base_score = next(
                (p for p in base_playbooks if p.get("slug") == score.slug),
                None,
            )
            if not base_score:
                # Baseline might be a single-playbook file
                base_structural = baseline.get("structural_score")
            else:
                base_structural = base_score.get("structural_score")

            if base_structural is not None:
                delta = score.structural_score - base_structural
                if delta < -MAX_REGRESSION_PTS:
                    regression_alerts.append({
                        "slug": score.slug,
                        "before": base_structural,
                        "after": score.structural_score,
                        "delta": delta,
                    })

        # Rule 3: fixture present
        fixture_crit = next(
            (c for c in score.criteria if c.name == "test_fixture_present"),
            None,
        )
        if fixture_crit and not fixture_crit.passed:
            missing_fixture.append(score.slug)

    passed = not (below_bar or regression_alerts or missing_fixture)
    return ValidationResult(
        passed=passed,
        below_bar=below_bar,
        regression_alerts=regression_alerts,
        missing_fixture=missing_fixture,
    )


def enforce(
    report: EvalReport,
    strict: bool = False,
) -> None:
    """
    Validate and raise ``SystemExit(1)`` if checks fail.

    Parameters
    ----------
    strict:
        When True, treat missing_fixture violations as failures (default False,
        since not all playbooks have external fixture files yet).
    """
    import sys

    result = validate_report(report)
    if strict:
        passed = result.passed
    else:
        # Relax: ignore missing_fixture in non-strict mode
        passed = not (result.below_bar or result.regression_alerts)

    print(result.summary())
    if not passed:
        sys.exit(1)
