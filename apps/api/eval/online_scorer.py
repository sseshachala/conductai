"""
Online eval scorer — scores every production run against mechanical quality
criteria and (20% sample) an LLM-as-judge, then queues low-scoring runs as
fixture promotion candidates.

Called from the worker daemon after a run completes. Never blocks the run
execution path — always runs in the background thread.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

# Runs grading below this threshold are queued as fixture candidates
_CANDIDATE_GRADES = {"C", "D", "F"}

# Fields to scrub from state dicts (keys matched case-insensitively)
_PII_KEYS = {
    "email", "author", "assignee", "login", "name", "committer",
    "sender", "pusher", "owner", "user", "requested_reviewers",
}

# Regex for inline email addresses anywhere in string values
_EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")


# ── Anonymization ─────────────────────────────────────────────────────────────

def _hash(value: str) -> str:
    """Deterministic 8-char alias — same input always produces same alias."""
    return "anon-" + hashlib.sha256(value.encode()).hexdigest()[:8]


def _scrub_value(value: Any) -> Any:
    if isinstance(value, str):
        return _EMAIL_RE.sub("[redacted]", value)
    if isinstance(value, dict):
        return _scrub_dict(value)
    if isinstance(value, list):
        return [_scrub_value(v) for v in value]
    return value


def _scrub_dict(d: dict) -> dict:
    out: dict = {}
    for k, v in d.items():
        if k.lower() in _PII_KEYS:
            if isinstance(v, str) and v:
                out[k] = _hash(v)
            elif isinstance(v, dict):
                out[k] = {"id": _hash(str(v.get("id", v))), "_redacted": True}
            elif isinstance(v, list):
                out[k] = ["[redacted]"] * len(v)
            else:
                out[k] = "[redacted]"
        else:
            out[k] = _scrub_value(v)
    return out


def anonymize_state(state: dict) -> dict:
    """
    Return a copy of run state with PII removed.

    - Repository full_name → deterministic hash alias
    - Email addresses in any string value → [redacted]
    - Author/assignee/login/name fields → hashed alias
    - Lists of users → length-preserving [redacted] list
    - Kept intact: outcome type, token counts, timing, block execution path,
      trigger type, PR/issue numbers, label names, CI status strings
    """
    anon = _scrub_dict(state)

    # Hash repo full_name specifically (owner/repo format)
    repo = anon.get("repository") or anon.get("repo") or {}
    if isinstance(repo, dict):
        for key in ("full_name", "clone_url", "html_url", "url", "ssh_url"):
            if key in repo and isinstance(repo[key], str):
                repo[key] = _hash(repo[key])

    return anon


# ── Token count helper ────────────────────────────────────────────────────────

def _count_tokens(state: dict) -> int:
    """Sum input+output tokens from all block outputs in state."""
    total = 0
    for v in state.values():
        if not isinstance(v, dict):
            continue
        total += v.get("input_tokens", 0) or 0
        total += v.get("output_tokens", 0) or 0
        total += v.get("total_tokens", 0) or 0
    return total


# ── Slug resolution ───────────────────────────────────────────────────────────

def _resolve_slug(workflow_version_id: str, db: Session) -> str | None:
    from sqlalchemy import text
    row = db.execute(
        text("""
            SELECT w.playbook_slug
            FROM workflow_versions wv
            JOIN workflows w ON w.id = wv.workflow_id
            WHERE wv.id = :wv_id
            LIMIT 1
        """),
        {"wv_id": workflow_version_id},
    ).fetchone()
    return row[0] if row else None


def _resolve_workflow_id(workflow_version_id: str, db: Session) -> str | None:
    from sqlalchemy import text
    row = db.execute(
        text("SELECT workflow_id FROM workflow_versions WHERE id = :id LIMIT 1"),
        {"id": workflow_version_id},
    ).fetchone()
    return str(row[0]) if row else None


# ── Mechanical scoring ────────────────────────────────────────────────────────

def _mechanical_score(run_status: str, outcome: dict | None, state: dict, token_count: int) -> tuple[int, int]:
    """
    Return (score, max) for the 4 mechanical quality criteria (40 pts).

    run_succeeded    15 pts
    outcome_detected 10 pts
    artifact_produced 10 pts
    token_budget      5 pts  (passes if < 50k tokens)
    """
    score = 0

    if run_status == "succeeded":
        score += 15

    if outcome and outcome.get("type"):
        score += 10

    if outcome and outcome.get("artifact_url"):
        score += 10

    if token_count < 50_000:
        score += 5

    return score, 40


# ── Grade from pct ────────────────────────────────────────────────────────────

def _grade(pct: float) -> str:
    if pct >= 90: return "A"
    if pct >= 75: return "B"
    if pct >= 60: return "C"
    if pct >= 40: return "D"
    return "F"


# ── Main entry point ──────────────────────────────────────────────────────────

def score_run_online(run_id: str, db: Session, judge: bool = False) -> None:
    """
    Score a completed production run and persist the result.

    - Always runs mechanical scoring (~1ms)
    - Runs LLM-as-judge only when judge=True (caller controls 20% sampling)
    - Queues run as a fixture candidate if grade is C/D/F
    - Skips silently if the run has already been scored
    """
    from app.models.run import Run
    from app.models.run_online_score import RunOnlineScore, RunFixtureCandidate

    # Idempotency — skip if already scored
    existing = db.query(RunOnlineScore).filter_by(run_id=run_id).first()
    if existing:
        return

    run = db.query(Run).filter_by(id=run_id).first()
    if not run:
        log.warning("online_scorer.run_not_found", run_id=run_id)
        return

    slug = _resolve_slug(str(run.workflow_version_id), db)
    if not slug:
        log.debug("online_scorer.no_slug", run_id=run_id)
        return

    workflow_id = _resolve_workflow_id(str(run.workflow_version_id), db)
    state = run.state or {}
    outcome = run.outcome or {}
    token_count = _count_tokens(state)

    # Mechanical score
    mech_score, mech_max = _mechanical_score(run.status, outcome, state, token_count)

    # Optional LLM judge
    judge_score, judge_max = 0, 0
    if judge:
        try:
            from eval.judge import judge_output, extract_brain_output
            brain_text = extract_brain_output(state)
            if brain_text:
                judge_result = judge_output(slug, brain_text)
                if judge_result and not judge_result.failed:
                    for c in judge_result.to_criteria():
                        judge_score += c.points_earned
                    judge_max = 30
        except Exception as exc:
            log.warning("online_scorer.judge_failed", run_id=run_id, error=str(exc))
            judge = False

    total_score = mech_score + judge_score
    total_max = mech_max + judge_max
    pct = (total_score / total_max * 100) if total_max > 0 else 0.0
    grade = _grade(pct)

    anon_outcome = anonymize_state(outcome) if outcome else None

    score_row = RunOnlineScore(
        id=uuid.uuid4(),
        run_id=run_id,
        workflow_id=workflow_id,
        slug=slug,
        grade=grade,
        pct=round(pct, 2),
        mechanical_score=mech_score,
        mechanical_max=mech_max,
        judge_score=judge_score,
        judge_max=judge_max,
        judge_used=judge,
        run_status=run.status,
        outcome_type=outcome.get("type") if outcome else None,
        token_count=token_count,
        anonymized_outcome=anon_outcome,
        scored_at=datetime.now(timezone.utc),
    )
    db.add(score_row)

    if grade in _CANDIDATE_GRADES:
        anon_trigger = anonymize_state(state.get("trigger", state.get("__trigger__", {})))
        anon_state = anonymize_state(state)

        already = db.query(RunFixtureCandidate).filter_by(run_id=run_id).first()
        if not already:
            db.add(RunFixtureCandidate(
                id=uuid.uuid4(),
                run_id=run_id,
                slug=slug,
                grade=grade,
                pct=round(pct, 2),
                anon_trigger_payload=anon_trigger,
                anon_state=anon_state,
                expected_outcome_type=outcome.get("type") if outcome else None,
                status="pending",
                created_at=datetime.now(timezone.utc),
            ))

    db.commit()
    log.info(
        "online_scorer.scored",
        run_id=run_id,
        slug=slug,
        grade=grade,
        pct=round(pct, 1),
        judge_used=judge,
        candidate=grade in _CANDIDATE_GRADES,
    )
