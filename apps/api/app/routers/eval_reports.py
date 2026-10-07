"""Eval harness report / fixture / structural-run endpoints and the report cache
(split from eval.py).

Owns the shared ``/eval`` APIRouter; eval.py imports ``router`` from here and
registers the live-job, benchmark and candidate endpoints after these, which
keeps the original route registration order.
"""
from __future__ import annotations
import threading
import time
from typing import Annotated, Any
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import get_db

log = structlog.get_logger("app.routers.eval")


router = APIRouter(prefix="/eval", tags=["eval"])


# ── in-process cache — structural eval is deterministic so 5-min TTL is fine ──

_cache: dict[str, Any] = {}
_CACHE_TTL = 300  # seconds
_cache_lock = threading.Lock()


def _cached_report() -> dict[str, Any]:
    """Return a cached structural report dict, recomputing if stale."""
    now = time.monotonic()
    if "report" in _cache and (now - _cache.get("computed_at", 0)) < _CACHE_TTL:
        return _cache["report"]

    with _cache_lock:
        # Double-check inside lock so only one request recomputes when stale.
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


def _enrich_summary(report: dict[str, Any]) -> dict[str, Any]:
    """Add grade_counts and top_playbooks to report summary in-place and return it."""
    grade_counts: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
    for p in report.get("playbooks", []):
        g = p.get("grade", "F")
        grade_counts[g] = grade_counts.get(g, 0) + 1

    top = sorted(report.get("playbooks", []), key=lambda x: -x["pct"])[:5]
    report["summary"] = {
        **report.get("summary", {}),
        "grade_counts": grade_counts,
        "top_playbooks": [
            {"slug": p["slug"], "grade": p["grade"], "pct": p["pct"]}
            for p in top
        ],
    }
    return report


def _run_one_fresh(slug: str) -> dict[str, Any]:
    """
    Run structural eval for a single playbook, bypass cache, patch result back
    into the cached report so subsequent reads reflect the fresh score.
    """
    try:
        from eval.runner import run_one
        report = run_one(slug, live=False)
        if not report.scores:
            raise ValueError(f"No scores returned for '{slug}'")
        score_dict = report._to_dict()["playbooks"][0]

        # Patch the cached report in-place so the list view stays consistent
        if "report" in _cache:
            playbooks = _cache["report"].get("playbooks", [])
            for i, p in enumerate(playbooks):
                if p["slug"] == slug:
                    playbooks[i] = score_dict
                    break
            else:
                playbooks.append(score_dict)
            # Recompute summary so grade_counts/top_playbooks reflect the fresh score
            _enrich_summary(_cache["report"])

        log.info("eval.run_one", slug=slug, grade=score_dict["grade"], pct=score_dict["pct"])
        return score_dict
    except HTTPException:
        raise
    except Exception as e:
        log.error("eval.run_one_failed", slug=slug, error=str(e))
        raise HTTPException(status_code=500, detail=f"Eval run failed for '{slug}': {e}")


def _serialise_fixture(f: Any) -> dict[str, Any]:
    """Convert a PlaybookFixture dataclass to a JSON-safe dict."""
    return {
        "slug": f.slug,
        "source": f.source,
        "trigger_payload": f.trigger_payload,
        "initial_state": f.initial_state,
        "expected_outcome_type": f.expected_outcome_type,
        "expected_artifact_keys": f.expected_artifact_keys,
        "extra_assertions": f.extra_assertions,
    }


def _require_super_admin(
    x_admin_secret: Annotated[str | None, Header()] = None,
) -> None:
    """Gate platform-only eval actions with the server ADMIN_SECRET."""
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Requires super admin")


# ── score endpoints ───────────────────────────────────────────────────────────

@router.get("/report")
def get_eval_report(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
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
def get_eval_summary():
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
def get_playbook_eval(slug: str):
    """
    Return the full score breakdown for a single playbook, including the
    test fixture (trigger_payload, expected outcome, artifact keys).
    """
    report = _cached_report()
    match = next((p for p in report["playbooks"] if p["slug"] == slug), None)
    if not match:
        known = [p["slug"] for p in report["playbooks"]]
        raise HTTPException(
            status_code=404,
            detail=f"Playbook '{slug}' not found. Known slugs: {known}",
        )

    # Attach fixture data inline so the detail page has everything in one call
    try:
        from eval.fixtures import load_fixture
        fixture = load_fixture(slug)
        fixture_data = _serialise_fixture(fixture) if fixture else None
    except Exception:
        fixture_data = None

    return {**match, "fixture": fixture_data}


@router.get("/playbooks")
def list_playbook_evals():
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
            "total_criteria": len(p["criteria"]),
        }
        for p in report["playbooks"]
    ]


# ── fixture endpoints ─────────────────────────────────────────────────────────

@router.get("/fixtures")
def list_fixtures(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.eval.view")),
):
    """
    Return a lightweight list of all playbook fixtures.

    Response: [{slug, source, expected_outcome_type, expected_artifact_keys,
                has_payload, has_initial_state}, ...]
    """
    try:
        from eval.fixtures import load_fixtures
        fixtures = load_fixtures()
    except Exception as e:
        log.error("eval.fixtures_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load fixtures: {e}")

    return [
        {
            "slug": f.slug,
            "source": f.source,
            "expected_outcome_type": f.expected_outcome_type,
            "expected_artifact_keys": f.expected_artifact_keys,
            "has_payload": bool(f.trigger_payload),
            "has_initial_state": bool(f.initial_state),
            "scenario_count": getattr(f, "scenario_count", 1),
            "scenario_tags": getattr(f, "scenario_tags", []),
        }
        for f in fixtures
    ]


@router.get("/fixtures/{slug}")
def get_fixture(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.eval.view")),
):
    """
    Return the full fixture for a single playbook: trigger payload,
    initial state, expected outcome type, and artifact keys.
    """
    try:
        from eval.fixtures import load_fixture
        fixture = load_fixture(slug)
    except Exception as e:
        log.error("eval.fixture_load_failed", slug=slug, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load fixture: {e}")

    if fixture is None:
        raise HTTPException(status_code=404, detail=f"No fixture found for '{slug}'")

    return _serialise_fixture(fixture)


# ── on-demand run endpoints ───────────────────────────────────────────────────

@router.post("/run/{slug}")
def run_playbook_eval(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.eval.view")),
):
    """
    Re-run structural eval for a single playbook right now, bypassing the
    5-minute cache.  Returns the fresh score with criteria breakdown and
    fixture data — identical shape to GET /eval/playbooks/{slug}.

    Use this from the UI "Run" button on the eval detail page.
    """
    # Verify the slug exists before running
    try:
        from eval.fixtures import load_fixture
        fixture = load_fixture(slug)
    except Exception:
        fixture = None

    if fixture is None:
        raise HTTPException(status_code=404, detail=f"No playbook found with slug '{slug}'")

    score_dict = _run_one_fresh(slug)

    fixture_data = _serialise_fixture(fixture)
    return {**score_dict, "fixture": fixture_data}


@router.post("/run")
def run_all_evals(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.eval.view")),
):
    """
    Re-run structural eval for all playbooks right now, replacing the cache.
    Returns the full report — same shape as GET /eval/report.

    Admin/editor only (takes ~200ms, no need to gate harder but don't let
    anonymous callers hammer it).
    """
    _cache.clear()
    report = _cached_report()
    return _enrich_summary(report)
