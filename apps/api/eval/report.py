"""
Report generation for the Conduct eval harness.

EvalReport wraps a list of PlaybookScore objects and knows how to render
them as a human-readable table or a structured JSON benchmark document.

The JSON format is stable across releases — downstream tools (dashboard,
CI checks, NORTHSTAR moat tracker) can parse it without breaking.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from eval.scorer import PlaybookScore, CriterionResult


# ── report container ──────────────────────────────────────────────────────────

@dataclass
class EvalReport:
    scores: list[PlaybookScore]
    live_mode: bool = False
    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    # ── aggregate stats ───────────────────────────────────────────────────────

    @property
    def total_playbooks(self) -> int:
        return len(self.scores)

    @property
    def passing(self) -> list[PlaybookScore]:
        return [s for s in self.scores if s.grade not in ("D", "F")]

    @property
    def failing(self) -> list[PlaybookScore]:
        return [s for s in self.scores if s.grade in ("D", "F")]

    @property
    def average_pct(self) -> float:
        if not self.scores:
            return 0.0
        return sum(s.pct for s in self.scores) / len(self.scores)

    # ── rendering ─────────────────────────────────────────────────────────────

    def summary(self) -> str:
        """Return a compact human-readable summary for the terminal."""
        lines: list[str] = []

        mode_tag = "LIVE" if self.live_mode else "STRUCTURAL"
        lines.append(f"\nConduct Eval Harness — {mode_tag} mode")
        lines.append(f"Generated: {self.generated_at}")
        lines.append("")

        # Header
        lines.append(f"  {'Playbook':<30}  {'Score':>6}  {'Max':>4}  {'Pct':>5}  Grade  Issues")
        lines.append(f"  {'-'*30}  {'------':>6}  {'----':>4}  {'-----':>5}  -----  ------")

        for s in sorted(self.scores, key=lambda x: -x.pct):
            failures = s.failing_criteria()
            issues = f"{len(failures)} failing" if failures else "all pass"
            lines.append(
                f"  {s.slug:<30}  {s.total_score:>6}  {s.total_max:>4}  "
                f"{s.pct:>5.1f}%  {s.grade:<5}  {issues}"
            )

        lines.append("")
        lines.append(
            f"  {self.total_playbooks} playbooks evaluated  |  "
            f"{len(self.passing)} passing  |  {len(self.failing)} failing  |  "
            f"avg {self.average_pct:.1f}%"
        )

        # Detail section: list failing criteria for each playbook
        failing_playbooks = [s for s in self.scores if s.failing_criteria()]
        if failing_playbooks:
            lines.append("")
            lines.append("Failing criteria:")
            for s in failing_playbooks:
                lines.append(f"\n  [{s.slug}]")
                for c in s.failing_criteria():
                    lines.append(
                        f"    x {c.name} (+{c.points_possible} pts)  {c.detail}"
                    )

        lines.append("")
        return "\n".join(lines)

    def to_json(self, indent: int = 2) -> str:
        """Return a stable JSON representation of the full report."""
        return json.dumps(self._to_dict(), indent=indent)

    def _to_dict(self) -> dict[str, Any]:
        return {
            "version": "1",
            "generated_at": self.generated_at,
            "live_mode": self.live_mode,
            "summary": {
                "total_playbooks": self.total_playbooks,
                "passing": len(self.passing),
                "failing": len(self.failing),
                "average_pct": round(self.average_pct, 1),
            },
            "playbooks": [
                {
                    "slug": s.slug,
                    "structural_score": s.structural_score,
                    "structural_max": s.structural_max,
                    "quality_score": s.quality_score,
                    "quality_max": s.quality_max,
                    "total_score": s.total_score,
                    "total_max": s.total_max,
                    "pct": round(s.pct, 1),
                    "grade": s.grade,
                    "criteria": [
                        {
                            "name": c.name,
                            "passed": c.passed,
                            "points_earned": c.points_earned,
                            "points_possible": c.points_possible,
                            "detail": c.detail,
                        }
                        for c in s.criteria
                    ],
                }
                for s in sorted(self.scores, key=lambda x: -x.pct)
            ],
        }

    # ── promotion loop helpers ────────────────────────────────────────────────

    def promotion_candidates(self, min_grade: str = "B") -> list[PlaybookScore]:
        """
        Return playbooks scoring at or above ``min_grade``.

        Used by the community playbook promotion loop to surface high-quality
        contributions for review and merge into the main playbook library.
        """
        grade_order = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
        threshold = grade_order.get(min_grade, 1)
        return [
            s for s in self.scores
            if grade_order.get(s.grade, 4) <= threshold
        ]

    def regression_alerts(self, baseline: "EvalReport") -> list[dict[str, Any]]:
        """
        Compare this report against a baseline and return regressions.
        A regression is any playbook whose total_score dropped by more than 5 pts.
        """
        base_by_slug = {s.slug: s for s in baseline.scores}
        alerts = []
        for s in self.scores:
            base = base_by_slug.get(s.slug)
            if base and (base.total_score - s.total_score) > 5:
                alerts.append({
                    "slug": s.slug,
                    "before": base.total_score,
                    "after": s.total_score,
                    "delta": s.total_score - base.total_score,
                })
        return alerts
