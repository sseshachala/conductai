"""Bounded platform investigations over existing audit, receipt and run stores."""
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import check_permission
from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.agent_identity.models import AgentIdentity
from app.modules.guard.models import GuardAuditEvent
from app.modules.glens.trial_evidence import TrialEvidenceQuery, TrialEvidenceResult, TrialEventEvidence
from app.modules.glens.trial_accounting import attach_trial_accounting


class PlatformEvidenceQuery(TrialEvidenceQuery):
    surface: Literal["all", "guard", "gateway", "workflow", "trial"] = "all"
    run_id: UUID | None = None
    decision: Literal["allowed", "warned", "blocked", "approval"] | None = None


class PlatformEventEvidence(TrialEventEvidence):
    source: str | None = None


class StepEvidence(BaseModel):
    source_id: UUID
    block_id: str | None
    kind: str
    recorded_at: datetime


class RunEvidence(BaseModel):
    source_id: UUID
    workflow_id: UUID
    workflow_name: str
    status: str
    current_block_id: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    steps: list[StepEvidence] = Field(default_factory=list)
    steps_total: int = 0


class PlatformEvidenceResult(TrialEvidenceResult):
    surface: Literal["all", "guard", "gateway", "workflow", "trial"] = "all"
    run_id: UUID | None = None
    decision: str | None = None
    records: list[PlatformEventEvidence] = Field(default_factory=list)
    runs_status: Literal["not_requested", "ok", "empty", "partial", "denied", "unavailable"] = "not_requested"
    runs: list[RunEvidence] = Field(default_factory=list)
    runs_total: int | None = None
    limitations: list[str] = Field(default_factory=lambda: [
        "Only recorded, authorized activity is covered; missing evidence is not zero activity.",
        "A policy decision, provider attempt and workflow outcome are distinct facts.",
        "Run selection uses creation time; returned step history may extend beyond that window.",
    ])


def _permission(db, workspace_id, user_id, permission):
    check_permission(user_id=user_id, workspace_id=str(workspace_id), credentials=None,
                     db=db, permission=permission)


def _member(db, workspace_id, user_id):
    return isinstance(user_id, str) and db.execute(text(
        "SELECT 1 FROM workspace_users WHERE workspace_id=:ws AND clerk_user_id=:uid"
    ), {"ws": str(workspace_id), "uid": user_id}).fetchone() is not None


def _read_runs(db, user_id, query, evidence):
    if query.surface not in {"all", "workflow"}:
        return
    try:
        _permission(db, evidence.workspace_id, user_id, "platform.runs.view")
        if query.scope == "workspace":
            _permission(db, evidence.workspace_id, user_id, "guard.activity.view_all")
        stmt = select(
            Run.id, Workflow.id.label("workflow_id"), Workflow.name.label("workflow_name"),
            Run.status, Run.current_block_id, Run.created_at, Run.started_at, Run.completed_at,
            func.count().over().label("total"),
        ).join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id).join(
            Workflow, WorkflowVersion.workflow_id == Workflow.id,
        ).where(Run.workspace_id == evidence.workspace_id, Workflow.workspace_id == evidence.workspace_id,
                Run.created_at >= query.since, Run.created_at < query.until)
        if query.scope == "own":
            stmt = stmt.where(Run.triggered_by == user_id)
        if query.run_id:
            stmt = stmt.where(Run.id == query.run_id)
        # Request-ID filters describe calls, not entire runs. Do not return
        # unrelated runs as if they were linked to those calls.
        if query.request_ids is not None and query.run_id is None:
            return
        rows = db.execute(stmt.order_by(Run.created_at.desc(), Run.id.desc()).limit(query.limit)).all()
        evidence.runs_total = rows[0].total if rows else 0
        evidence.runs = [RunEvidence(
            source_id=r.id, workflow_id=r.workflow_id, workflow_name=r.workflow_name,
            status=r.status, current_block_id=r.current_block_id, created_at=r.created_at,
            started_at=r.started_at, completed_at=r.completed_at,
        ) for r in rows]
        evidence.runs_status = "partial" if evidence.runs_total > len(rows) else "ok" if rows else "empty"
        if not rows:
            return
        # Bound step history independently for each authorized run.
        ranked = select(
            RunEvent.id, RunEvent.run_id, RunEvent.block_id, RunEvent.kind, RunEvent.created_at,
            func.row_number().over(partition_by=RunEvent.run_id,
                                   order_by=(RunEvent.created_at.desc(), RunEvent.id.desc())).label("rank"),
            func.count().over(partition_by=RunEvent.run_id).label("total"),
        ).where(RunEvent.run_id.in_([r.id for r in rows])).subquery()
        steps = db.execute(select(ranked).where(ranked.c.rank <= 10).order_by(ranked.c.rank)).mappings()
        indexed = {r.source_id: r for r in evidence.runs}
        for step in steps:
            run = indexed[step["run_id"]]
            run.steps_total = step["total"]
            run.steps.append(StepEvidence(source_id=step["id"], block_id=step["block_id"],
                                          kind=step["kind"], recorded_at=step["created_at"]))
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        evidence.runs_status = "denied"


def read_platform_evidence(db, workspace_id, user_id, query: PlatformEvidenceQuery):
    evidence = PlatformEvidenceResult(
        status="denied", workspace_id=workspace_id, scope=query.scope,
        retrieved_at=datetime.now(timezone.utc), since=query.since, until=query.until,
        request_ids=query.request_ids, limit=query.limit, surface=query.surface,
        run_id=query.run_id, decision=query.decision,
    )
    try:
        if not _member(db, workspace_id, user_id):
            return evidence
        _permission(db, workspace_id, user_id,
                    f"guard.activity.view_{'all' if query.scope == 'workspace' else 'own'}")
        event, identity = GuardAuditEvent, AgentIdentity
        stmt = select(
            event.id, event.request_id, event.agent_identity_id, event.ts, event.decision,
            event.rule_id, event.policy_hash, event.provider, event.model,
            event.lifecycle_state, event.execution_status, event.source,
            func.count().over().label("total"),
        ).outerjoin(identity, (event.agent_identity_id == identity.id)
                    & (identity.workspace_id == evidence.workspace_id)).where(
            event.workspace_id == evidence.workspace_id, event.ts >= query.since, event.ts < query.until,
        )
        if query.scope == "own":
            stmt = stmt.where(or_(event.clerk_user_id == user_id, identity.owner_user_id == user_id))
        if query.surface == "trial":
            stmt = stmt.where(identity.source == "conduct_trial")
        elif query.surface == "guard":
            stmt = stmt.where(event.source.in_(["hook", "mcp"]))
        elif query.surface == "gateway":
            stmt = stmt.where(event.source.in_(["gateway", "proxy"]))
        elif query.surface == "workflow":
            linked_run = select(LlmAttemptReceipt.id).where(
                LlmAttemptReceipt.workspace_id == evidence.workspace_id,
                LlmAttemptReceipt.request_id == event.request_id,
                LlmAttemptReceipt.workflow_run_id.is_not(None),
            ).exists()
            stmt = stmt.where(or_(event.source == "workflow", event.conductai_run_id.is_not(None), linked_run))
        if query.run_id:
            receipt_link = select(LlmAttemptReceipt.id).where(
                LlmAttemptReceipt.workspace_id == evidence.workspace_id,
                LlmAttemptReceipt.request_id == event.request_id,
                LlmAttemptReceipt.workflow_run_id == query.run_id,
            ).exists()
            stmt = stmt.where(or_(event.conductai_run_id == str(query.run_id), receipt_link))
        if query.request_ids is not None:
            stmt = stmt.where(event.request_id.in_(query.request_ids))
        if query.decision:
            stmt = stmt.where(event.decision == query.decision)
        rows = db.execute(stmt.order_by(event.ts.desc(), event.id.desc()).limit(query.limit)).all()
        evidence.total_matching = rows[0].total if rows else 0
        evidence.has_more = evidence.total_matching > len(rows)
        evidence.records = [PlatformEventEvidence(
            source_id=r.id, request_id=r.request_id, agent_identity_id=r.agent_identity_id or "",
            recorded_at=r.ts.replace(tzinfo=timezone.utc) if r.ts.tzinfo is None else r.ts,
            decision=r.decision, rule_id=r.rule_id, policy_hash=r.policy_hash, provider=r.provider,
            model=r.model, lifecycle_state=r.lifecycle_state, execution_status=r.execution_status,
            source=r.source,
        ) for r in rows]
        evidence.status = "partial" if evidence.has_more else "ok" if rows else "empty"
        if query.request_ids and set(query.request_ids) - {r.request_id for r in evidence.records}:
            if rows:
                evidence.status = "partial"
            evidence.limitations.append("Some requested IDs were not returned in this authorized window.")
        attach_trial_accounting(db, user_id, evidence)
        _read_runs(db, user_id, query, evidence)
        return evidence
    except HTTPException as exc:
        if exc.status_code != 403:
            raise
        return evidence
    except SQLAlchemyError:
        # Do not keep partially assembled counts after a failed query.
        return PlatformEvidenceResult(
            **{**evidence.model_dump(exclude={"records", "runs", "accounting_totals"}),
               "status": "unavailable", "total_matching": None, "has_more": None,
               "accounting_status": "unavailable", "runs_status": "unavailable", "runs_total": None},
        )
