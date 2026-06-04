"""
GET /dashboard  — outcome-based summary for the workspace.

Outcome counting strategy (COALESCE, no regression):
  1. If run.outcome is set (new runs), read outcome["type"] directly.
  2. If run.outcome is NULL (pre-migration runs), fall back to state heuristics.
This means historical metrics never drop to zero during rollout.
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.run import Run
from app.models.run_trace import RunTrace
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.guard.models import GuardAuditEvent
from app.schemas.run import _extract_trigger_summary


def _extract_repo(state: dict | None) -> str | None:
    if not state:
        return None
    trigger = state.get("_trigger") or {}
    return (trigger.get("repository") or {}).get("full_name") or None

# Sonnet pricing (per 1M tokens) used for cost estimates — approximate
_INPUT_COST_PER_M  = 3.0
_OUTPUT_COST_PER_M = 15.0

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# Statuses that need human attention — mirrors runUtils.needsAttention()
ATTENTION_STATUSES = ["failed", "paused", "cancelled"]

# Playbook slugs that produce each outcome type (used for heuristic fallback)
_REVIEW_SLUGS   = {"pr_reviewer", "copilot_reviewer", "security_scanner"}
_INCIDENT_SLUGS = {"incident_responder", "postmortem_drafter"}
_TRIAGE_SLUGS   = {"issue_triage"}
_PR_SLUGS       = {"autopilot_quick", "autopilot_full", "autopilot_approved",
                   "security_patch_updater", "dependency_updater"}


def _outcome_type(run: Run, slug: str | None) -> str | None:
    """
    Return the semantic outcome type for a run.
    Reads run.outcome["type"] if set (new runs), otherwise falls back to heuristics.
    """
    if run.outcome and isinstance(run.outcome, dict):
        return run.outcome.get("type")

    # Heuristic fallback for pre-migration runs (outcome column is NULL)
    if run.status != "succeeded":
        return None
    state = run.state or {}

    def _find(key: str) -> bool:
        if state.get(key):
            return True
        return any(isinstance(v, dict) and v.get(key) for v in state.values())

    if slug in _PR_SLUGS and (_find("pr_url")):
        return "pr_opened"
    if slug in _REVIEW_SLUGS:
        return "review_completed"
    if slug in _TRIAGE_SLUGS:
        return "issue_triaged"
    if slug in _INCIDENT_SLUGS:
        return "incident_investigated"
    return None


class OutcomeStats(BaseModel):
    prs_opened: int
    issues_triaged: int
    reviews_completed: int
    incidents_investigated: int
    successful_automations: int
    failed_automations: int


class AgentHealth(BaseModel):
    workflow_id: str
    name: str
    playbook_slug: str | None
    run_count: int
    succeeded_count: int
    failed_count: int
    success_rate: float
    last_run_status: str | None
    last_run_at: str | None


class AttentionRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    trigger_summary: str | None
    created_at: str
    repo: str | None = None


class RecentRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    started_at: str | None
    created_at: str
    repo: str | None = None


class AgentTokenUsage(BaseModel):
    workflow_id: str
    name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class TokenUsage(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    by_agent: list[AgentTokenUsage]


class DashboardOut(BaseModel):
    outcomes: OutcomeStats
    needs_attention: list[AttentionRun]
    agent_health: list[AgentHealth]
    recent_activity: list[RecentRun]
    token_usage: TokenUsage
    guard_blocks_today: int


@router.get("", response_model=DashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
):
    today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = datetime.now(timezone.utc) - timedelta(days=7)

    # ── Week runs with playbook_slug for COALESCE outcome resolution ──────────
    week_rows = (
        db.query(Run, Workflow.playbook_slug.label("slug"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id, Run.created_at >= week_start)
        .all()
    )

    prs_opened = issues_triaged = reviews_completed = incidents_investigated = 0
    successful_automations = failed_automations = 0

    for run, slug in week_rows:
        if run.status == "succeeded":
            successful_automations += 1
            ot = _outcome_type(run, slug)
            if ot == "pr_opened":
                prs_opened += 1
            elif ot == "issue_triaged":
                issues_triaged += 1
            elif ot == "review_completed":
                reviews_completed += 1
            elif ot == "incident_investigated":
                incidents_investigated += 1
        elif run.status == "failed":
            failed_automations += 1

    outcomes = OutcomeStats(
        prs_opened=prs_opened,
        issues_triaged=issues_triaged,
        reviews_completed=reviews_completed,
        incidents_investigated=incidents_investigated,
        successful_automations=successful_automations,
        failed_automations=failed_automations,
    )

    # ── Needs Attention — failed/paused/cancelled, aligned with runUtils ──────
    attention_rows = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Workflow.workspace_id == workspace_id,
            Run.status.in_(ATTENTION_STATUSES),
        )
        .order_by(Run.created_at.desc())
        .limit(10)
        .all()
    )

    needs_attention = [
        AttentionRun(
            run_id=str(run.id),
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            status=run.status,
            triggered_by=run.triggered_by,
            trigger_summary=_extract_trigger_summary(run.state),
            created_at=run.created_at.isoformat(),
            repo=_extract_repo(run.state),
        )
        for run, wf_id, wf_name in attention_rows
    ]

    # ── Agent Health — all-time aggregation ──────────────────────────────────
    wf_agg = (
        db.query(
            Workflow.id.label("wf_id"),
            Workflow.name.label("wf_name"),
            Workflow.playbook_slug,
            func.count(Run.id).label("run_count"),
            func.sum(case((Run.status == "succeeded", 1), else_=0)).label("succeeded"),
            func.sum(case((Run.status == "failed", 1), else_=0)).label("failed"),
            func.max(Run.created_at).label("last_run_at"),
        )
        .join(WorkflowVersion, WorkflowVersion.workflow_id == Workflow.id)
        .outerjoin(Run, Run.workflow_version_id == WorkflowVersion.id)
        .filter(Workflow.workspace_id == workspace_id)
        .group_by(Workflow.id, Workflow.name, Workflow.playbook_slug)
        .order_by(func.max(Run.created_at).desc().nullslast())
        .all()
    )

    wf_ids = [row.wf_id for row in wf_agg]
    last_status_map: dict[str, str] = {}
    if wf_ids:
        max_run_sq = (
            db.query(
                WorkflowVersion.workflow_id.label("wf_id"),
                func.max(Run.created_at).label("max_at"),
            )
            .join(Run, Run.workflow_version_id == WorkflowVersion.id)
            .filter(WorkflowVersion.workflow_id.in_(wf_ids))
            .group_by(WorkflowVersion.workflow_id)
            .subquery()
        )
        last_runs = (
            db.query(WorkflowVersion.workflow_id.label("wf_id"), Run.status)
            .join(Run, Run.workflow_version_id == WorkflowVersion.id)
            .join(
                max_run_sq,
                (WorkflowVersion.workflow_id == max_run_sq.c.wf_id)
                & (Run.created_at == max_run_sq.c.max_at),
            )
            .all()
        )
        last_status_map = {str(row.wf_id): row.status for row in last_runs}

    agent_health = []
    for row in wf_agg:
        rc = row.run_count or 0
        sc = row.succeeded or 0
        fc = row.failed or 0
        rate = round((sc / rc) * 100, 1) if rc else 0.0
        agent_health.append(AgentHealth(
            workflow_id=str(row.wf_id),
            name=row.wf_name,
            playbook_slug=row.playbook_slug,
            run_count=rc,
            succeeded_count=sc,
            failed_count=fc,
            success_rate=rate,
            last_run_status=last_status_map.get(str(row.wf_id)),
            last_run_at=row.last_run_at.isoformat() if row.last_run_at else None,
        ))

    # ── Recent Activity — last 5 runs ────────────────────────────────────────
    recent_rows = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, WorkflowVersion.id == Run.workflow_version_id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id)
        .order_by(Run.created_at.desc())
        .limit(5)
        .all()
    )

    recent_activity = [
        RecentRun(
            run_id=str(run.id),
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            status=run.status,
            triggered_by=run.triggered_by,
            started_at=run.started_at.isoformat() if run.started_at else None,
            created_at=run.created_at.isoformat(),
            repo=_extract_repo(run.state),
        )
        for run, wf_id, wf_name in recent_rows
    ]

    # ── Token usage — all-time, aggregated from run_traces ───────────────────
    token_rows = (
        db.query(
            Workflow.id.label("wf_id"),
            Workflow.name.label("wf_name"),
            func.coalesce(func.sum(RunTrace.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(RunTrace.output_tokens), 0).label("output_tokens"),
        )
        .join(WorkflowVersion, WorkflowVersion.workflow_id == Workflow.id)
        .join(Run, Run.workflow_version_id == WorkflowVersion.id)
        .join(RunTrace, RunTrace.run_id == Run.id)
        .filter(Workflow.workspace_id == workspace_id)
        .group_by(Workflow.id, Workflow.name)
        .order_by(func.sum(RunTrace.input_tokens + RunTrace.output_tokens).desc().nullslast())
        .all()
    )

    def _cost(inp: int, out: int) -> float:
        return round((inp * _INPUT_COST_PER_M + out * _OUTPUT_COST_PER_M) / 1_000_000, 4)

    by_agent = [
        AgentTokenUsage(
            workflow_id=str(row.wf_id),
            name=row.wf_name,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.input_tokens + row.output_tokens,
            estimated_cost_usd=_cost(row.input_tokens, row.output_tokens),
        )
        for row in token_rows
    ]
    total_input  = sum(a.input_tokens for a in by_agent)
    total_output = sum(a.output_tokens for a in by_agent)
    token_usage = TokenUsage(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
        estimated_cost_usd=_cost(total_input, total_output),
        by_agent=by_agent,
    )

    # ── Guard blocks today — count "blocked" audit events since midnight UTC ──
    guard_blocks_today: int = (
        db.query(func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == workspace_id,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= today_midnight,
        )
        .scalar()
        or 0
    )

    return DashboardOut(
        outcomes=outcomes,
        needs_attention=needs_attention,
        agent_health=agent_health,
        recent_activity=recent_activity,
        token_usage=token_usage,
        guard_blocks_today=guard_blocks_today,
    )
