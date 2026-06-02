"""
Eval harness API — exposes playbook quality scores and fixtures to the frontend.

GET  /eval/report              — full structural report (all playbooks), cached 5 min
GET  /eval/summary             — aggregate stats only (for dashboard cards)
GET  /eval/playbooks           — lightweight list: slug, grade, pct, failing_criteria
GET  /eval/playbooks/{slug}    — single playbook score + criteria breakdown + fixture
GET  /eval/fixtures            — list all fixtures (slug, source, payload preview)
GET  /eval/fixtures/{slug}     — full fixture: payload, initial_state, expected outcome
POST /eval/run/{slug}          — re-run structural eval for one playbook (bypasses cache)
POST /eval/run                 — re-run structural eval for all playbooks (busts cache)
POST /eval/live/{slug}         — super-admin only: queue a live eval run, returns job_id
GET  /eval/jobs/{job_id}       — super-admin only: poll live job status

All endpoints require at least viewer role.  /eval/report requires admin.
Structural scoring is fast (~10ms per playbook) so on-demand runs are cheap.
Live eval runs real LLM calls and is gated by X-Admin-Secret / ADMIN_SECRET.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.config import settings
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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


# ── live eval job store ───────────────────────────────────────────────────────
#
# Jobs are kept in-process.  A dict keyed by job_id with a lock for safe
# concurrent writes from background threads.  We cap the store at 100 entries
# (oldest removed first) so it never grows unbounded.

_JOB_STATUS = Literal["queued", "running", "done", "failed"]
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()
_JOBS_MAX = 100


def _job_create(slug: str) -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        if len(_jobs) >= _JOBS_MAX:
            # Evict the oldest entry
            oldest = next(iter(_jobs))
            del _jobs[oldest]
        _jobs[job_id] = {
            "job_id": job_id,
            "slug": slug,
            "status": "queued",
            "result": None,
            "error": None,
            "queued_at": time.time(),
            "started_at": None,
            "finished_at": None,
        }
    return job_id


def _job_update(job_id: str, **kwargs: Any) -> None:
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id].update(kwargs)


def _job_get(job_id: str) -> dict[str, Any] | None:
    with _jobs_lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None


def _resolve_anthropic_key(workspace_id: str, db: Session) -> str | None:
    """
    Resolve the Anthropic API key for a workspace using the same priority
    order as the executor:
      1. anthropic integration credential (handle="anthropic", field "api_key")
      2. env_vars credential (flat key ANTHROPIC_API_KEY or anthropic_api_key)
      3. platform-level ANTHROPIC_API_KEY env var (fallback for dev/self-hosted)
    """
    import os
    try:
        from app.models.integration import Integration
        from app.models.environment import Environment as _Env
        from app.core.crypto import decrypt

        default_env = db.query(_Env).filter(
            _Env.workspace_id == workspace_id,
            _Env.name == "Default",
        ).first()

        cred_rows = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == default_env.id,
        ).all() if default_env else []

        for row in cred_rows:
            if not row.encrypted_credentials:
                continue
            creds = decrypt(row.encrypted_credentials)
            if row.handle == "anthropic":
                key = creds.get("api_key")
                if key:
                    return key
            if row.handle == "env_vars":
                key = creds.get("ANTHROPIC_API_KEY") or creds.get("anthropic_api_key")
                if key:
                    return key
    except Exception as exc:
        log.warning("eval.live_key_lookup_failed", error=str(exc))

    # Platform-level fallback (dev / self-hosted without vault)
    return os.environ.get("ANTHROPIC_API_KEY") or None


def _run_live_background(job_id: str, slug: str, anthropic_api_key: str) -> None:
    """
    Background thread: execute live eval and write result into the job store.

    The api_key is passed directly into run_one() which scopes it to the
    AnthropicClient mock patch for this call only.  No process-level
    os.environ mutation — concurrent jobs from different workspaces are safe.
    """
    _job_update(job_id, status="running", started_at=time.time())
    log.info("eval.live_started", job_id=job_id, slug=slug)
    try:
        from eval.runner import run_one
        from eval.fixtures import load_fixture

        report = run_one(slug, live=True, api_key=anthropic_api_key)
        if not report.scores:
            raise ValueError(f"No scores returned for '{slug}'")

        score_dict = report._to_dict()["playbooks"][0]

        # Attach fixture inline — same shape as GET /eval/playbooks/{slug}
        fixture = load_fixture(slug)
        fixture_data = _serialise_fixture(fixture) if fixture else None
        result = {**score_dict, "fixture": fixture_data}

        _job_update(
            job_id,
            status="done",
            result=result,
            finished_at=time.time(),
        )
        log.info("eval.live_done", job_id=job_id, slug=slug, grade=score_dict["grade"])

    except Exception as exc:
        _job_update(
            job_id,
            status="failed",
            error=str(exc),
            finished_at=time.time(),
        )
        log.error("eval.live_failed", job_id=job_id, slug=slug, error=str(exc))


# ── live eval endpoints ───────────────────────────────────────────────────────

@router.post("/live/{slug}")
def start_live_eval(
    slug: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """
    Queue a live (real LLM) eval run for a single playbook.

    Returns immediately with a job_id.  Poll GET /eval/jobs/{job_id} to
    track progress.  Live eval calls the real executor with mocked external
    integrations (GitHub/Slack) but a real Anthropic LLM call.

    Requires workspace admin role. The run typically takes 15-60 seconds
    depending on playbook complexity.
    """
    # Verify the slug exists before queuing
    try:
        from eval.fixtures import load_fixture
        fixture = load_fixture(slug)
    except Exception:
        fixture = None

    if fixture is None:
        raise HTTPException(status_code=404, detail=f"No playbook found with slug '{slug}'")

    # Resolve the Anthropic key from the workspace credential vault.
    # Falls back to the platform-level env var for dev / self-hosted setups.
    anthropic_key = _resolve_anthropic_key(workspace_id, db)
    if not anthropic_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "No Anthropic API key found for this workspace. "
                "Add it in Settings → Credentials as an 'anthropic' integration "
                "or set ANTHROPIC_API_KEY in your Default environment."
            ),
        )

    job_id = _job_create(slug)
    background_tasks.add_task(_run_live_background, job_id, slug, anthropic_key)

    log.info("eval.live_queued", job_id=job_id, slug=slug)
    return {
        "job_id": job_id,
        "slug": slug,
        "status": "queued",
        "poll_url": f"/eval/jobs/{job_id}",
    }


# ── benchmark / baseline endpoints ───────────────────────────────────────────
#
# Editions are frozen score snapshots committed to reports/baselines/.
# These endpoints are public-readable (viewer role) — the data is already
# committed to git so there is no sensitive information to guard.

@router.get("/benchmark/editions")
def list_benchmark_editions():
    """
    Return all committed benchmark editions (newest first).

    Each edition is a frozen snapshot of eval scores published via
    ``python -m eval.runner --publish``.  The data lives in
    ``reports/baselines/edition-*.json``.

    Response: [{slug, published_at, model, summary, playbook_count, top_playbooks}, ...]
    """
    try:
        from eval.benchmark import list_editions
        return list_editions()
    except Exception as e:
        log.error("eval.benchmark_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load benchmark editions: {e}")


@router.get("/benchmark/editions/{edition_slug}")
def get_benchmark_edition(edition_slug: str):
    """
    Return the full manifest for a single benchmark edition.

    Response: { edition, published_at, model, summary, playbooks: [...] }
    """
    try:
        from eval.benchmark import get_edition
        edition = get_edition(edition_slug)
    except Exception as e:
        log.error("eval.benchmark_edition_failed", slug=edition_slug, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load edition '{edition_slug}': {e}")

    if edition is None:
        raise HTTPException(
            status_code=404,
            detail=f"Edition '{edition_slug}' not found. Use GET /eval/benchmark/editions to list available editions.",
        )
    return edition


@router.get("/benchmark/baselines")
def list_playbook_baselines(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
):
    """
    Return all single-playbook baseline files.

    These are written by ``python -m eval.runner --playbook pr_reviewer --publish``.
    Response: [{file, slug, model, grade, pct, baseline_published_at}, ...]
    """
    try:
        from eval.benchmark import list_playbook_baselines as _list
        return _list()
    except Exception as e:
        log.error("eval.baselines_list_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load baselines: {e}")


@router.get("/candidates")
def list_fixture_candidates(
    slug: str | None = None,
    status: str = "pending",
    limit: int = 50,
    _: None = Depends(_require_super_admin),
    db: Session = Depends(get_db),
):
    """
    List production runs queued as fixture promotion candidates.

    Query params:
      slug    — filter by playbook slug
      status  — pending | promoted | dismissed (default: pending)
      limit   — max rows (default: 50)
    """
    from app.models.run_online_score import RunFixtureCandidate
    q = db.query(RunFixtureCandidate).filter(RunFixtureCandidate.status == status)
    if slug:
        q = q.filter(RunFixtureCandidate.slug == slug)
    rows = q.order_by(RunFixtureCandidate.created_at.desc()).limit(limit).all()
    return [
        {
            "id": str(r.id),
            "run_id": str(r.run_id),
            "slug": r.slug,
            "grade": r.grade,
            "pct": float(r.pct),
            "expected_outcome_type": r.expected_outcome_type,
            "anon_trigger_payload": r.anon_trigger_payload,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/candidates/{candidate_id}/promote")
def promote_fixture_candidate(
    candidate_id: str,
    _: None = Depends(_require_super_admin),
    db: Session = Depends(get_db),
):
    """
    Promote a fixture candidate by opening a GitHub PR that appends the
    anonymized trigger payload as a new scenario in the playbook's YAML fixture.
    """
    from datetime import datetime, timezone
    import yaml
    import httpx
    from app.models.run_online_score import RunFixtureCandidate

    row = db.query(RunFixtureCandidate).filter_by(id=candidate_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Candidate is already {row.status}")

    from app.routers.credentials import _github_token
    from app.core.auth import DEV_WORKSPACE_ID

    # Use the platform workspace's GitHub token (set in Settings → Environments)
    try:
        token = _github_token(DEV_WORKSPACE_ID, db)
    except Exception:
        raise HTTPException(status_code=503, detail="GitHub credentials not configured — add a GITHUB_TOKEN in Settings → Environments")

    # Derive repo from the workflow connected to this run
    from sqlalchemy import text as _text
    repo_row = db.execute(
        _text("""
            SELECT w.github_hook_repo FROM runs r
            JOIN workflow_versions wv ON wv.id = r.workflow_version_id
            JOIN workflows w ON w.id = wv.workflow_id
            WHERE r.id = :run_id LIMIT 1
        """),
        {"run_id": str(row.run_id)},
    ).fetchone()
    repo = repo_row[0] if repo_row and repo_row[0] else settings.github_promotion_repo
    if not repo:
        raise HTTPException(status_code=503, detail="Could not determine target repo — set GITHUB_PROMOTION_REPO or connect a GitHub repo to the workflow")
    fixture_path = f"apps/api/eval/fixtures/{row.slug}.yaml"
    branch = f"fixture/promote-{str(row.id)[:8]}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        base = f"https://api.github.com/repos/{repo}"

        # Get default branch SHA
        ref_res = httpx.get(f"{base}/git/ref/heads/main", headers=headers, timeout=10)
        ref_res.raise_for_status()
        sha = ref_res.json()["object"]["sha"]

        # Create branch
        httpx.post(f"{base}/git/refs", headers=headers, timeout=10, json={
            "ref": f"refs/heads/{branch}", "sha": sha
        }).raise_for_status()

        # Get current fixture file content
        file_res = httpx.get(f"{base}/contents/{fixture_path}", headers=headers, timeout=10)
        if file_res.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Fixture file not found: {fixture_path}")
        file_res.raise_for_status()
        file_data = file_res.json()
        current_content = __import__("base64").b64decode(file_data["content"]).decode()
        file_sha = file_data["sha"]

        # Build new scenario block
        new_scenario = {
            "id": f"promoted_{str(row.id)[:8]}",
            "label": f"(promoted) Grade {row.grade} run — {row.expected_outcome_type or 'unknown outcome'}",
            "tags": ["positive"] if row.grade in ("A", "B") else ["negative"],
            "expected_outcome_type": row.expected_outcome_type,
            "trigger_payload": row.anon_trigger_payload or {},
        }
        scenario_yaml = "\n  " + yaml.dump(
            new_scenario, default_flow_style=False, allow_unicode=True
        ).replace("\n", "\n  ").rstrip()
        updated_content = current_content.rstrip() + f"\n{scenario_yaml}\n"

        # Push updated file
        import base64
        httpx.put(
            f"{base}/contents/{fixture_path}",
            headers=headers,
            timeout=10,
            json={
                "message": f"fixture: promote run {str(row.run_id)[:8]} ({row.slug}, grade {row.grade})",
                "content": base64.b64encode(updated_content.encode()).decode(),
                "sha": file_sha,
                "branch": branch,
            },
        ).raise_for_status()

        # Open PR
        pr_res = httpx.post(f"{base}/pulls", headers=headers, timeout=10, json={
            "title": f"fixture({row.slug}): promote production run as eval scenario",
            "body": (
                f"Auto-promoted from fixture candidate `{candidate_id}`.\n\n"
                f"- Playbook: `{row.slug}`\n"
                f"- Grade: **{row.grade}** ({float(row.pct):.0f}%)\n"
                f"- Expected outcome: `{row.expected_outcome_type}`\n"
                f"- Run ID: `{row.run_id}` (anonymized)\n\n"
                f"Review the appended scenario in `{fixture_path}` before merging."
            ),
            "head": branch,
            "base": "main",
        })
        pr_res.raise_for_status()
        pr_url = pr_res.json()["html_url"]

    except HTTPException:
        raise
    except Exception as exc:
        log.error("candidates.promote_failed", candidate_id=candidate_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Failed to open PR: {exc}")

    row.status = "promoted"
    row.promoted_at = datetime.now(timezone.utc)
    row.promoted_pr_url = pr_url
    db.commit()

    return {"status": "promoted", "pr_url": pr_url}


@router.post("/candidates/{candidate_id}/dismiss")
def dismiss_fixture_candidate(
    candidate_id: str,
    _: None = Depends(_require_super_admin),
    db: Session = Depends(get_db),
):
    """Mark a fixture candidate as dismissed (won't appear in pending list)."""
    from app.models.run_online_score import RunFixtureCandidate

    row = db.query(RunFixtureCandidate).filter_by(id=candidate_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"Candidate is already {row.status}")

    row.status = "dismissed"
    db.commit()
    return {"status": "dismissed", "id": candidate_id}


@router.get("/scenarios/{slug}")
def get_scenario_set(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
):
    """
    Return all scenarios for a playbook that has a multi-scenario fixture file.

    Response: { slug, description, scenario_count, positive_count, negative_count, scenarios: [...] }
    """
    try:
        from eval.fixtures import load_scenario_set
        scenario_set = load_scenario_set(slug)
    except Exception as e:
        log.error("eval.scenarios_load_failed", slug=slug, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to load scenarios for '{slug}': {e}")

    if scenario_set is None:
        raise HTTPException(
            status_code=404,
            detail=f"No multi-scenario fixture file found for '{slug}'. "
                   f"Only the following playbooks have multi-scenario fixtures: "
                   f"pr_reviewer, security_scanner, issue_triage, incident_responder.",
        )

    return {
        "slug": scenario_set.slug,
        "description": scenario_set.description,
        "scenario_count": len(scenario_set.scenarios),
        "positive_count": len(scenario_set.positive_scenarios),
        "negative_count": len(scenario_set.negative_scenarios),
        "scenarios": [
            {
                "id": s.id,
                "label": s.label,
                "tags": s.tags,
                "trigger_payload": s.trigger_payload,
                "initial_state": s.initial_state,
                "expected_outcome_type": s.expected_outcome_type,
                "expected_artifact_keys": s.expected_artifact_keys,
                "extra_assertions": s.extra_assertions,
                "expected_should_review": s.expected_should_review,
                "expected_should_scan": s.expected_should_scan,
            }
            for s in scenario_set.scenarios
        ],
    }


@router.get("/jobs/{job_id}")
def get_live_job(
    job_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """
    Poll the status of a live eval job.

    Response shape:
      {
        job_id, slug, status,          # queued | running | done | failed
        queued_at, started_at,         # Unix timestamps (float), null if not yet
        finished_at,
        result,                        # full score + fixture when status == "done"
        error,                         # error string when status == "failed"
      }
    """
    job = _job_get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job
