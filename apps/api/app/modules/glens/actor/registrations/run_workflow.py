"""#1298 — trigger a workflow run from Lens or MCP via the actor substrate.

Compact re-implementation of the essential path from
`apps.api.app.routers.runs.create_run` — resolve workflow, build initial
state, enrich contract, insert Run, enqueue. Skips canvas-only features
(per-run guard override, dry_run, per-run persona) — those are workflow-
level defaults for Lens callers.

ponytail: initial state minimal — Lens caller sends {inputs?}. Add canvas-style
overrides only if callers actually need them (currently: none do).
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger(__name__)


def _resolve_workflow(db, workspace_id: str, name_or_id: str):
    """Match by UUID id first, then by playbook_slug, then by name (case-insensitive)."""
    from app.models.workflow import Workflow

    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        return None

    # UUID hit
    try:
        wid = _uuid.UUID(str(name_or_id))
        wf = db.query(Workflow).filter(
            Workflow.id == wid, Workflow.workspace_id == ws,
        ).first()
        if wf:
            return wf
    except ValueError:
        pass

    # Playbook slug hit
    wf = db.query(Workflow).filter(
        Workflow.workspace_id == ws,
        Workflow.playbook_slug == str(name_or_id),
    ).first()
    if wf:
        return wf

    # Case-insensitive name hit
    wf = db.query(Workflow).filter(
        Workflow.workspace_id == ws,
        Workflow.name.ilike(str(name_or_id)),
    ).first()
    return wf


def _propose_run_workflow(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    name_or_id = str(args.get("name_or_id") or "").strip()
    if not name_or_id:
        return ProposeResult(rejected=True, reason="name_or_id required",
                             summary="", resolved_input={})

    workflow = _resolve_workflow(ctx.db, ctx.workspace_id, name_or_id)
    if not workflow:
        return ProposeResult(
            rejected=True, reason=f"No workflow matches '{name_or_id}'",
            summary="", resolved_input={},
        )

    if not workflow.current_version_id:
        return ProposeResult(
            rejected=True, reason=f"Workflow '{workflow.name}' has no published version",
            summary="", resolved_input={},
        )

    warnings: list[str] = []
    if not getattr(workflow, "guard_enabled", True):
        warnings.append("Guard is disabled on this workflow.")

    inputs = args.get("inputs")
    if inputs is not None and not isinstance(inputs, dict):
        return ProposeResult(rejected=True, reason="inputs must be an object",
                             summary="", resolved_input={})

    summary = f"Run '{workflow.name}' now"
    if inputs:
        summary += f" with {len(inputs)} input(s)"

    return ProposeResult(
        summary=summary,
        resolved_input={
            "workflow_id": str(workflow.id),
            "workflow_name": workflow.name,
            "inputs": inputs or {},
        },
        warnings=warnings,
    )


def _execute_run_workflow(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Insert a Run and enqueue. Reuses the same models + Redis queue the
    CLI/API path uses. No per-run overrides — Lens callers get workflow
    defaults."""
    from app.models.run import Run
    from app.models.workflow import Workflow
    from app.routers.runs import _enqueue_run
    from app.runtime.run_contract import enrich_run_state_contract

    workflow_id = _uuid.UUID(resolved["workflow_id"])
    workflow = ctx.db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise ValueError(f"workflow {workflow_id} disappeared between propose and execute")

    initial_state: dict[str, Any] = dict(resolved.get("inputs") or {})
    # ponytail: Lens callers don't set contract inputs today — enrich with
    # workflow defaults and let the runtime handle missing pieces.
    initial_state = enrich_run_state_contract(
        initial_state,
        source="lens",
        trigger_provider="lens",
        workflow_id=str(workflow.id),
        workspace_id=ctx.workspace_id,
        max_turns=getattr(workflow, "default_max_turns", None) or 20,
    )

    run = Run(
        workflow_version_id=workflow.current_version_id,
        workspace_id=workflow.workspace_id,
        triggered_by=f"lens:{ctx.clerk_user_id or 'unknown'}",
        status="pending",
        state=initial_state,
        max_turns=getattr(workflow, "default_max_turns", None) or 20,
        # #1480 PR 14 — thread the originating Lens session through so the
        # worker's publish_run_status / publish_run_block_event calls have
        # somewhere to route SSE events. Without this the RunBubble in
        # chat never gets the block timeline because publisher no-ops on
        # session_id=NULL.
        session_id=ctx.session_id,
    )
    ctx.db.add(run)
    ctx.db.commit()
    ctx.db.refresh(run)

    try:
        _enqueue_run(str(run.id))
    except Exception as exc:
        log.warning("lens.actor.enqueue_failed", run_id=str(run.id), err=str(exc))
        # Run row is still in the DB and will be picked up on the next
        # worker heartbeat — don't fail the confirm.

    return {
        "run_id": str(run.id),
        "workflow_id": str(workflow.id),
        "workflow_name": workflow.name,
        "status": run.status,
    }


default_action_registry.register(ActionSpec(
    name="run_workflow",
    guard_permission="platform.workflows.run",
    propose=_propose_run_workflow,
    execute=_execute_run_workflow,
    description=(
        "Trigger a workflow run by playbook slug, workflow ID, or name. Two-step: "
        "returns a pending action for the user to confirm; the confirm click "
        "inserts the Run + enqueues it — same code path as `conduct run`."
    ),
))
