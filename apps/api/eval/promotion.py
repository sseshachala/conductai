"""
Playbook promotion loop.

Reads eval scores and writes PlaybookSubmission rows.  Run after eval to
surface high-quality playbooks for review or auto-promotion.

Auto-promotion rules
---------------------
  Grade A (>=90%)  -> status = "promoted"   (builtin playbooks are always A)
  Grade B (80-89%) -> status = "pending"    (needs human review)
  Grade C/D/F      -> status = "needs_work" (score too low, flag for improvement)

Usage
-----
  from eval.promotion import promote
  from eval.runner import run_all

  report = run_all()
  submissions = promote(report)

  # With an explicit DB session:
  submissions = promote(report, db_session=my_session)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from eval.report import EvalReport
from eval.scorer import PlaybookScore

log = logging.getLogger(__name__)


def _status_for_grade(grade: str) -> str:
    """Map a letter grade to a promotion status string."""
    if grade == "A":
        return "promoted"
    if grade == "B":
        return "pending"
    return "needs_work"


def promote(
    report: EvalReport,
    db_session: Any = None,
) -> list[Any]:
    """
    Write/update one PlaybookSubmission row per score in the report.

    If *db_session* is None, creates its own session via SessionLocal.
    Returns the list of upserted submission objects.

    The function is intentionally simple — it does not attempt a true SQL
    upsert because different DB backends handle that differently.  Instead it
    queries for an existing row by slug and overwrites it, or inserts a new
    row if none exists.
    """
    from app.models.playbook_submission import PlaybookSubmission

    _own_session = db_session is None
    if _own_session:
        from app.core.database import SessionLocal
        db_session = SessionLocal()

    now = datetime.now(timezone.utc)
    results: list[PlaybookSubmission] = []

    try:
        for score in report.scores:
            status = _status_for_grade(score.grade)
            promoted_at = now if status == "promoted" else None

            # Serialize full criteria list for audit trail
            criteria_json = json.dumps(
                [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "points_earned": c.points_earned,
                        "points_possible": c.points_possible,
                        "detail": c.detail,
                    }
                    for c in score.criteria
                ]
            )

            # Check for an existing row by slug (latest eval wins)
            existing = (
                db_session.query(PlaybookSubmission)
                .filter(PlaybookSubmission.slug == score.slug)
                .first()
            )

            if existing is not None:
                existing.structural_score = score.structural_score
                existing.quality_score = score.quality_score
                existing.grade = score.grade
                existing.status = status
                existing.criteria_json = criteria_json
                existing.eval_run_at = now
                existing.promoted_at = promoted_at
                existing.updated_at = now
                submission = existing
            else:
                submission = PlaybookSubmission(
                    slug=score.slug,
                    source="builtin",
                    structural_score=score.structural_score,
                    quality_score=score.quality_score,
                    grade=score.grade,
                    status=status,
                    criteria_json=criteria_json,
                    eval_run_at=now,
                    promoted_at=promoted_at,
                )
                db_session.add(submission)

            results.append(submission)
            log.info(
                "promote.scored",
                slug=score.slug,
                grade=score.grade,
                status=status,
            )

        db_session.commit()
        log.info("promote.done", count=len(results))

    except Exception:
        db_session.rollback()
        raise
    finally:
        if _own_session:
            db_session.close()

    return results
