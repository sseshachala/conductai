"""
Eval harness API — exposes playbook quality scores to the frontend.

GET  /eval/report          — full structural report (all playbooks), cached 5 min
GET  /eval/playbooks/{slug} — single playbook detail with criteria breakdown
GET  /eval/summary          — aggregate stats only (for dashboard cards)

All endpoints are admin-only.  Structural scoring is fast (~50ms for all 18
playbooks) so we cache the result for 5 minutes to avoid recomputing on every
page load.  Live-mode scoring (real LLM calls) is not exposed here — run it
from the CLI: python -m eval.runner --live --json --out reports/eval_live.json
"""
from __future__ import annotations

import time
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/eval", tags=["eval"])

# ── in-process cache — structural eval is deterministic so 5-min TTL is fine ──

_cache: dict[str, Any] = {}
_CACHE_TTL = 300  # seconds


def _cached_report() -> dict[str, Any]:
    """Return a cached structural report dict, recomputing if stale."""
    now = time.monotonic()
    if "report" in _cache and (now - _cache.get("computed_at", 0)) < _CACHE_TTL:
        return _cache["report"]

    try:
        from eval.runner import run_all
        report = run_all(live=False)
        data = report._to_dict()
        _cache["report"] = data
        _cache["computed_at"] = now
        log.info("eval.report_computed", playbooks=data["summary"]["total_playbooks"])
        return data
    except Exception as e:
        log.error("eval.report_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Eval computation failed: {e}")


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/report")
def get_eval_report(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
    refresh: bool = False,
):
    """
    Return the full structural eval report for all playbooks.

    Pass ?refresh=true to force a cache bust (useful after deploying new
    playbook YAML files).
    """
    if refresh:
        _cache.clear()
    return _cached_report()


@router.get("/summary")
def get_eval_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return aggregate stats only — suitable for a dashboard card.

    Response shape:
      { total_playbooks, passing, failing, average_pct,
        grade_counts: {A, B, C, D, F},
        top_playbooks: [{slug, grade, pct}, ...] (top 5 by score) }
    """
    report = _cached_report()
    summary = report["summary"]

    grade_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for p in report["playbooks"]:
        g = p.get("grade", "F")
        grade_counts[g] = grade_counts.get(g, 0) + 1

    top = sorted(report["playbooks"], key=lambda x: -x["pct"])[:5]

    return {
        **summary,
        "grade_counts": grade_counts,
        "top_playbooks": [
            {"slug": p["slug"], "grade": p["grade"], "pct": p["pct"]}
            for p in top
        ],
        "generated_at": report["generated_at"],
    }


@router.get("/playbooks/{slug}")
def get_playbook_eval(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return the full score breakdown for a single playbook.

    Includes every scored criterion with pass/fail, points earned, and detail
    text — sufficient to render a detailed quality card in the UI.
    """
    report = _cached_report()
    match = next((p for p in report["playbooks"] if p["slug"] == slug), None)
    if not match:
        known = [p["slug"] for p in report["playbooks"]]
        raise HTTPException(
            status_code=404,
            detail=f"Playbook '{slug}' not found. Known slugs: {known}",
        )
    return match


@router.get("/playbooks")
def list_playbook_evals(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return a lightweight list of all playbooks with slug, grade, pct.
    Suitable for a table or grid — criteria detail omitted for payload size.
    """
    report = _cached_report()
    return [
        {
            "slug": p["slug"],
            "grade": p["grade"],
            "pct": p["pct"],
            "total_score": p["total_score"],
            "total_max": p["total_max"],
            "structural_score": p["structural_score"],
            "quality_score": p["quality_score"],
            "failing_criteria": sum(1 for c in p["criteria"] if not c["passed"]),
        }
        for p in report["playbooks"]
    ]
