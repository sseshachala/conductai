import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import redis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)

from app.core.auth import get_workspace_id, get_user_id, require_permission, audit, _verify_clerk_token, _clerk_enabled, DEV_WORKSPACE_ID, DEV_USER_ID
from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.models.project import Project
from app.schemas.run import RunCreate, RunDetailOut, RunOut, RunWithWorkflowOut
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract

router = APIRouter(prefix="/workflows/{workflow_id}/runs", tags=["runs"])

# ── Workspace-wide runs router ────────────────────────────────────────────────

workspace_runs_router = APIRouter(prefix="/runs", tags=["runs"])

QUEUE_KEY = "marshal:runs:queue"
QUEUE_MAX_DEPTH = 50_000  # hard cap — reject new runs when queue is this deep


def _enqueue_run(run_id: str) -> None:
    """Push run_id onto the Redis queue, refusing when queue is too deep."""
    r = _redis()
    depth = r.llen(QUEUE_KEY)
    if depth >= QUEUE_MAX_DEPTH:
        raise HTTPException(
            status_code=503,
            detail=f"Run queue is at capacity ({depth} pending). Try again shortly.",
        )
    r.rpush(QUEUE_KEY, run_id)


def get_workspace_id_sse(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    """Auth dependency for SSE endpoints.
    EventSource cannot set custom headers, so token and workspace_id come via query params."""
    auth_header = request.headers.get("Authorization", "")
    x_ws = request.headers.get("x-workspace-id") or request.query_params.get("workspace_id")

    if not _clerk_enabled():
        return x_ws or DEV_WORKSPACE_ID

    # Accept api_key from header OR query param (CLI streams can't always set headers)
    api_key_hdr = (
        request.headers.get("x-api-key")
        or request.query_params.get("api_key")
    )

    # Master server-level CLI key
    cli_key = settings.cli_api_key
    if cli_key and api_key_hdr == cli_key:
        if not settings.cli_workspace_id:
            raise HTTPException(status_code=500, detail="CLI_WORKSPACE_ID is not configured on the server")
        return settings.cli_workspace_id

    # Per-user cond_live_... API key
    if api_key_hdr and api_key_hdr.startswith("cond_live_"):
        import hashlib
        from app.models.conduct_api_key import ConductApiKey
        key_hash = hashlib.sha256(api_key_hdr.encode()).hexdigest()
        row = db.query(ConductApiKey).filter(ConductApiKey.key_hash == key_hash).first()
        if row and (row.expires_at is None or row.expires_at > datetime.now(timezone.utc)):
            row.last_used_at = datetime.now(timezone.utc)
            db.commit()
            return str(row.workspace_id)

    raw_token = None
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.removeprefix("Bearer ")
    elif request.query_params.get("token"):
        raw_token = request.query_params.get("token")

    if not raw_token:
        raise HTTPException(status_code=401, detail="Authorization required")

    claims = _verify_clerk_token(raw_token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    ws = x_ws or claims.get("org_id") or claims.get("sub")
    if not ws:
        raise HTTPException(status_code=401, detail="No workspace in token claims")
    return ws


def _get_user_id_from_request(request: Request) -> str:
    """Extract Clerk user_id from Authorization header or ?token= query param for SSE endpoints."""
    if not _clerk_enabled():
        return DEV_USER_ID
    auth_header = request.headers.get("Authorization", "")
    raw_token = None
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.removeprefix("Bearer ")
    elif request.query_params.get("token"):
        raw_token = request.query_params.get("token")
    if not raw_token:
        raise HTTPException(status_code=401, detail="Authorization required")
    claims = _verify_clerk_token(raw_token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")
    return user_id


def get_user_workspace_role_sse(
    request: Request,
    workspace_id: str = Depends(get_workspace_id_sse),
    db: Session = Depends(get_db),
) -> str:
    """Role-checking dependency for SSE endpoints (mirrors get_user_workspace_role)."""
    if not _clerk_enabled():
        return "admin"

    # API key auth — workspace was already validated by get_workspace_id_sse, grant admin
    api_key_val = request.headers.get("x-api-key") or request.query_params.get("api_key")
    if api_key_val:
        return "admin"

    user_id = _get_user_id_from_request(request)

    import re as _re
    if not _re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", workspace_id, _re.I):
        raise HTTPException(status_code=403, detail="Invalid workspace ID — please select a workspace")

    from sqlalchemy import text
    row = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()
    if not row:
        owner_row = db.execute(
            text("SELECT owner_id FROM workspaces WHERE id = :ws AND owner_id = :uid"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if not owner_row:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")
        return "admin"
    return row.role


def require_workspace_role_sse(*allowed_roles: str):
    """Role-gating factory for SSE endpoints (mirrors require_workspace_role)."""
    def _check(role: str = Depends(get_user_workspace_role_sse)) -> str:
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(allowed_roles)}")
        return role
    return _check


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _get_workflow(workflow_id: UUID, workspace_id: str, db: Session) -> Workflow:
    """Fetch workflow and verify it belongs to the caller's workspace."""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _get_run(run_id: UUID, workflow_id: UUID, db: Session, workspace_id: str | None = None) -> Run:
    """Fetch run and verify it belongs to the given workflow (prevents cross-tenant access).

    Pass workspace_id to additionally scope the run lookup to a specific tenant.
    Leave workspace_id=None only for callers (get_run) that intentionally allow
    cross-workspace lookup and perform their own membership check afterward.
    """
    version_ids = db.query(WorkflowVersion.id).filter(
        WorkflowVersion.workflow_id == workflow_id
    ).subquery()
    q = db.query(Run).filter(
        Run.id == run_id,
        Run.workflow_version_id.in_(version_ids),
    )
    if workspace_id:
        q = q.filter(Run.workspace_id == UUID(workspace_id))
    run = q.first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    _get_workflow(workflow_id, workspace_id, db)
    # Return runs across ALL versions so autosave version bumps don't hide history
    version_ids = db.query(WorkflowVersion.id).filter(
        WorkflowVersion.workflow_id == workflow_id
    ).subquery()
    return (
        db.query(Run)
        .filter(
            Run.workflow_version_id.in_(version_ids),
            Run.workspace_id == UUID(workspace_id),
        )
        .order_by(Run.created_at.desc())
        .all()
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    workflow_id: UUID,
    body: RunCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = _get_workflow(workflow_id, workspace_id, db)
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no published version")

    initial_state = body.initial_state or {}
    if body.dry_run:
        initial_state["__dry_run"] = True
    if not body.guard_enabled:
        initial_state["__guard_enabled"] = False

    try:
        initial_state = validate_run_start_inputs(initial_state)
    except InputContractError as err:
        raise HTTPException(status_code=422, detail=str(err))

    # If the caller didn't provide an explicit turn budget, estimate it server-side
    # so CLI and API callers get the same guard as the canvas preflight banner.
    max_turns = body.max_turns
    if not max_turns:
        from app.routers.workflows import _estimate_turns_for_graph
        issue = (
            initial_state.get("github_issue")
            or initial_state.get("_trigger", {}).get("issue")
            or initial_state.get("_trigger", {}).get("pull_request")
            or {}
        )
        try:
            graph = workflow.current_version.graph or {} if workflow.current_version else {}
            pf = _estimate_turns_for_graph(
                graph,
                issue.get("title", ""),
                issue.get("body", ""),
                workspace_id=workspace_id,
                db=db,
            )
            max_turns = pf["suggested_max_turns"]
        except Exception:
            max_turns = 20

    initial_state = enrich_run_state_contract(
        initial_state,
        source="manual",
        trigger_provider="manual",
        workflow_id=str(workflow_id),
        workspace_id=workspace_id,
        max_turns=max_turns,
    )

    run = Run(
        workflow_version_id=workflow.current_version_id,
        workspace_id=workflow.workspace_id,
        triggered_by=body.triggered_by,
        status="pending",
        state=initial_state,
        max_turns=max_turns,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        _enqueue_run(str(run.id))
    except HTTPException:
        raise
    except Exception as _enqueue_err:
        log.error("run.enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))
        raise HTTPException(
            status_code=503,
            detail="Run created but queue is unavailable. Retry in a moment.",
        )

    log.info("run.created", run_id=str(run.id), workspace_id=workspace_id, workflow_id=str(workflow_id))
    audit(db, workspace_id, "run.triggered",
          resource_type="run", resource_id=str(run.id),
          metadata={"workflow_id": str(workflow_id), "dry_run": body.dry_run})

    return run


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    user_id: str = Depends(get_user_id),
):
    # Look up the run directly by ID — don't gate on the cookie workspace so
    # trace URLs in Slack notifications work regardless of active workspace.
    run = (
        db.query(Run)
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .filter(Run.id == run_id, WorkflowVersion.workflow_id == workflow_id)
        .first()
    )
    if not run:
        log.warning("run.not_found", run_id=str(run_id), workflow_id=str(workflow_id))
        raise HTTPException(status_code=404, detail="Run not found")

    # Verify caller is a member of the run's actual workspace.
    from sqlalchemy import text
    actual_ws = str(run.workflow_version.workflow.workspace_id)
    row = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": actual_ws, "uid": user_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    return run


_RUN_CHANNEL_PREFIX = "marshal:run:"
_SSE_TIMEOUT_SECONDS = 1200  # close stream after 20 min; covers long E2B/Modal sandbox runs


def publish_run_event(run_id: str) -> None:
    """Notify SSE subscribers that a new event is available for this run."""
    try:
        _redis().publish(f"{_RUN_CHANNEL_PREFIX}{run_id}", "1")
    except Exception:
        pass


@router.get("/{run_id}/stream")
def stream_run_events(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id_sse),
    _role: str = Depends(require_workspace_role_sse("admin", "developer", "security", "viewer")),
):
    """SSE stream of run_events driven by Redis pub/sub — one DB query per notification."""
    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db, workspace_id=workspace_id)

    def event_generator():
        import time as _time
        from app.core.database import SessionLocal

        last_seen_created_at: datetime | None = None  # cursor for paginated DB queries
        stream_db = SessionLocal()
        pubsub = _redis().pubsub()
        pubsub.subscribe(f"{_RUN_CHANNEL_PREFIX}{str(run_id)}")
        deadline = _time.monotonic() + _SSE_TIMEOUT_SECONDS

        def flush_new_events():
            nonlocal last_seen_created_at
            # Only fetch events newer than the last one we saw — avoids full-table
            # scan on every Redis notification (perf fix for issue #535).
            q = stream_db.query(RunEvent).filter(RunEvent.run_id == run_id)
            if last_seen_created_at is not None:
                q = q.filter(RunEvent.created_at > last_seen_created_at)
            events = q.order_by(RunEvent.created_at).limit(100).all()
            for ev in events:
                last_seen_created_at = ev.created_at
                yield f"data: {json.dumps({'id': str(ev.id), 'kind': ev.kind, 'block_id': ev.block_id, 'payload': ev.payload})}\n\n"

        def is_terminal() -> str | None:
            stream_db.expire_all()
            current = stream_db.query(Run).filter(Run.id == run_id).first()
            return current.status if current and current.status in ("succeeded", "failed", "paused", "paused_for_clarification", "cancelled") else None

        try:
            # Flush any events already written before we subscribed
            yield from flush_new_events()
            terminal = is_terminal()
            if terminal:
                if terminal in ("paused", "paused_for_clarification"):
                    r = stream_db.query(Run).filter(Run.id == run_id).first()
                    yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': r.current_block_id if r else None, 'payload': {'status': terminal}})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Poll using get_message with a short timeout so the deadline is enforced.
            # pubsub.listen() has no timeout; get_message(timeout=N) yields control
            # every N seconds so we can check both the deadline and run status.
            _last_keepalive = _time.monotonic()
            _KEEPALIVE_INTERVAL = 15  # seconds — Render drops idle SSE after ~30s
            while _time.monotonic() < deadline:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message and message["type"] == "message":
                    yield from flush_new_events()
                    terminal = is_terminal()
                    if terminal:
                        if terminal == "paused":
                            r = stream_db.query(Run).filter(Run.id == run_id).first()
                            yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': r.current_block_id if r else None, 'payload': {}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return
                elif message is None:
                    # Emit SSE comment ping every 15s to prevent Render/proxy idle timeout.
                    now = _time.monotonic()
                    if now - _last_keepalive >= _KEEPALIVE_INTERVAL:
                        yield ": keepalive\n\n"
                        _last_keepalive = now
                    # No pub/sub message — poll DB periodically (every ~5 s) to catch
                    # runs that completed without publishing (e.g. Redis pub/sub miss).
                    terminal = is_terminal()
                    if terminal:
                        yield from flush_new_events()
                        if terminal == "paused":
                            r = stream_db.query(Run).filter(Run.id == run_id).first()
                            yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': r.current_block_id if r else None, 'payload': {}})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

            # Deadline reached — close the stream; client will reconnect.
            yield "data: {\"kind\": \"stream_timeout\"}\n\n"
        finally:
            pubsub.unsubscribe()
            pubsub.close()
            stream_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Approval endpoints ────────────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    decision: str  # "approved" or "rejected"
    approver: str | None = None


@router.get("/{run_id}/trace")
def get_run_trace(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    """Return the full AI conversation trace for a run — ordered by turn and role."""
    _get_workflow(workflow_id, workspace_id, db)
    _get_run(run_id, workflow_id, db, workspace_id=workspace_id)
    from app.models.run_trace import RunTrace
    rows = (
        db.query(RunTrace)
        .filter(RunTrace.run_id == run_id)
        .order_by(RunTrace.block_id, RunTrace.turn, RunTrace.created_at)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "block_id": r.block_id,
            "turn": r.turn,
            "role": r.role,
            "content": r.content,
            "tool_name": r.tool_name,
            "tool_input": r.tool_input,
            "tool_use_id": r.tool_use_id,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@router.post("/{run_id}/cancel")
def cancel_run(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """Mark a running or pending run as cancelled. The worker will abort on next check."""
    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db, workspace_id=workspace_id)
    if run.status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"Run cannot be cancelled (status: {run.status})")
    run.status = "cancelled"
    run.completed_at = _now()
    db.add(RunEvent(run_id=run_id, block_id=None, kind="run_cancelled", payload={"reason": "user_cancelled"}))
    db.commit()
    log.info("run.cancelled", run_id=str(run_id), workspace_id=workspace_id)
    return {"run_id": str(run_id), "status": "cancelled"}


@router.post("/{run_id}/approve")
def approve_run(
    workflow_id: UUID,
    run_id: UUID,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """
    Called by the human approver (or Slack webhook) to resume a paused run.
    Stores the decision in run.state and re-queues the run.
    """
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db, workspace_id=workspace_id)

    block_id = run.current_block_id
    if not block_id:
        raise HTTPException(status_code=400, detail="No approval block recorded on paused run")

    # Single atomic UPDATE: CAS on status='paused' + state merge in one statement.
    # If another request already resumed the run, the WHERE clause fails and
    # fetchone() returns None — no second writer can slip in between.
    from sqlalchemy import text as _text
    state = dict(run.state or {})
    state[f"__approval_{block_id}"] = body.decision
    if body.approver:
        state[f"__approver_{block_id}"] = body.approver
    cas_result = db.execute(
        _text(
            "UPDATE runs SET status='pending', paused_at=NULL, state=:state::jsonb "
            "WHERE id=:id AND status='paused' "
            "RETURNING id"
        ),
        {"state": json.dumps(state), "id": str(run_id)},
    ).fetchone()
    if not cas_result:
        current_status = db.query(Run).filter(Run.id == run_id).first()
        status_str = current_status.status if current_status else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Run is not paused — already resumed or in status '{status_str}'. "
                   "Duplicate approval ignored.",
        )

    event = RunEvent(
        run_id=run_id,
        block_id=block_id,
        kind="approval_received",
        payload={"decision": body.decision, "approver": body.approver},
    )
    db.add(event)
    db.commit()

    try:
        _enqueue_run(str(run_id))
    except HTTPException:
        raise
    except Exception as _enqueue_err:
        log.error("run.approve_enqueue_failed", run_id=str(run_id), error=str(_enqueue_err))
        raise HTTPException(status_code=503, detail="Approval recorded but queue unavailable — retry shortly")

    log.info("run.approved", run_id=str(run_id), workspace_id=workspace_id, approved_by=body.approver, decision=body.decision)
    return {"run_id": str(run_id), "decision": body.decision, "status": "queued"}


# ── Clarification endpoint ────────────────────────────────────────────────────

class ClarifyRequest(BaseModel):
    answer: str


@router.post("/{run_id}/clarify")
def clarify_run(
    workflow_id: UUID,
    run_id: UUID,
    body: ClarifyRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """
    Resume a run that is paused awaiting clarification.
    Stores the answer in run.state and re-queues the run.
    """
    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db, workspace_id=workspace_id)

    if run.status != "paused_for_clarification":
        raise HTTPException(status_code=400, detail=f"Run is not awaiting clarification (status: {run.status})")

    block_id = run.current_block_id
    if not block_id:
        raise HTTPException(status_code=400, detail="No block recorded on paused run")

    from sqlalchemy import text as _text
    state = dict(run.state or {})
    state[f"__clarification_{block_id}"] = body.answer

    cas_result = db.execute(
        _text(
            "UPDATE runs SET status='pending', paused_at=NULL, state=:state::jsonb "
            "WHERE id=:id AND status='paused_for_clarification' "
            "RETURNING id"
        ),
        {"state": json.dumps(state), "id": str(run_id)},
    ).fetchone()
    if not cas_result:
        current_status = db.query(Run).filter(Run.id == run_id).first()
        status_str = current_status.status if current_status else "unknown"
        raise HTTPException(
            status_code=409,
            detail=f"Run is not paused for clarification — already resumed or in status '{status_str}'.",
        )

    event = RunEvent(
        run_id=run_id,
        block_id=block_id,
        kind="clarification_answered",
        payload={"block_id": block_id, "answer_length": len(body.answer)},
    )
    db.add(event)
    db.commit()

    try:
        _enqueue_run(str(run_id))
    except HTTPException:
        raise
    except Exception as _enqueue_err:
        log.error("run.clarify_enqueue_failed", run_id=str(run_id), error=str(_enqueue_err))
        raise HTTPException(status_code=503, detail="Clarification recorded but queue unavailable — retry shortly")

    log.info("run.clarified", run_id=str(run_id), workspace_id=workspace_id, block_id=block_id)
    return {"run_id": str(run_id), "status": "resumed"}


# ── Workspace-wide run endpoints ──────────────────────────────────────────────

@workspace_runs_router.get("", response_model=list[RunWithWorkflowOut])
def list_all_runs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.runs.view")),
    status: str | None = None,
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: str | None = None,
    workflow_name: str | None = None,
    created_after: float | None = None,
):
    """All runs across all agents in the workspace, newest first.
    
    Filters:
    - status: pending/running/paused/succeeded/failed/cancelled
    - project_id: filter by project
    - repository: filter by repository (e.g., "owner/repo")
    - workflow_name: filter by workflow/playbook name
    - created_after: filter by creation timestamp (unix seconds or ISO datetime)
    """
    from sqlalchemy import text as _text, and_
    effective_workspace_id = workspace_id
    if project_id and user_id != DEV_USER_ID:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj and str(proj.workspace_id) != workspace_id:
            proj_ws = str(proj.workspace_id)
            member = db.execute(
                _text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
                {"ws": proj_ws, "uid": user_id},
            ).fetchone()
            if member:
                effective_workspace_id = proj_ws

    q = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"),
                 Workflow.project_id.label("proj_id"), Project.name.label("proj_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .outerjoin(Project, Workflow.project_id == Project.id)
        .filter(Workflow.workspace_id == effective_workspace_id)
        .order_by(Run.created_at.desc())
    )
    if status:
        q = q.filter(Run.status == status)
    if project_id:
        q = q.filter(Workflow.project_id == project_id)
    if workflow_name:
        q = q.filter(Workflow.name == workflow_name)
    if created_after is not None:
        try:
            # Try ISO datetime string first (e.g., "2026-05-28T12:34:56Z")
            if isinstance(created_after, str):
                after_dt = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            else:
                # Try Unix timestamp
                after_dt = datetime.fromtimestamp(created_after, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            # Fall back to no filter if parsing fails
            after_dt = None
        if after_dt:
            q = q.filter(Run.created_at >= after_dt)
    
    # Filter by repository - requires checking the state JSON
    # Only include runs where repo matches (extracted from _trigger.repository.full_name)
    if repository:
        q = q.filter(
            Run.state["_trigger"]["repository"]["full_name"].astext == repository
        )
    
    results = []
    for run, wf_id, wf_name, proj_id, proj_name in q.offset(offset).limit(limit).all():
        out = RunWithWorkflowOut(
            id=run.id,
            workflow_version_id=run.workflow_version_id,
            triggered_by=run.triggered_by,
            status=run.status,
            started_at=run.started_at,
            paused_at=run.paused_at,
            completed_at=run.completed_at,
            current_block_id=run.current_block_id,
            created_at=run.created_at,
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            project_id=str(proj_id) if proj_id else None,
            project_name=proj_name,
            state=run.state,
        )
        results.append(out)
    return results


@workspace_runs_router.get("/{run_id}", response_model=RunWithWorkflowOut)
def get_workspace_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    """Single run by ID, scoped to workspace, with workflow name."""
    row = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"),
                 Workflow.project_id.label("proj_id"), Project.name.label("proj_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .outerjoin(Project, Workflow.project_id == Project.id)
        .filter(Workflow.workspace_id == workspace_id, Run.id == run_id)
        .first()
    )
    if not row:
        log.warning("run.not_found", run_id=str(run_id), workspace_id=workspace_id)
        raise HTTPException(status_code=404, detail="Run not found")
    run, wf_id, wf_name, proj_id, proj_name = row
    return RunWithWorkflowOut(
        id=run.id,
        workflow_version_id=run.workflow_version_id,
        triggered_by=run.triggered_by,
        status=run.status,
        started_at=run.started_at,
        paused_at=run.paused_at,
        completed_at=run.completed_at,
        current_block_id=run.current_block_id,
        created_at=run.created_at,
        workflow_id=str(wf_id),
        workflow_name=wf_name,
        project_id=str(proj_id) if proj_id else None,
        project_name=proj_name,
    )
