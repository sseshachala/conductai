"""Workflow CRUD endpoints (split from workflows.py).

Owns the shared ``/workflows`` APIRouter. Route registration order is part of
the public contract, so the endpoint modules form an import chain:
workflows_crud -> workflows_validation -> workflows_yaml -> workflows. Each
module imports ``router`` from its predecessor, which guarantees the original
registration order regardless of which module is imported first.
"""
import pathlib
import structlog
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_permission, audit, _assert_workspace_member
from app.core.database import get_db
from app.dsl import (
    load_workflow_yaml,
    yaml_to_graph,
)
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowOut, WorkflowDetailOut
from app.compiler.compiler import compile_workflow
from app.compiler.stream import stream_compile_block
from app.routers.playbooks import (
    _GITHUB_WEBHOOK_EVENTS,
    _TEMPLATE_PLAYBOOKS,
)
from app.routers.workflows_git_hooks import (
    _deregister_git_webhook,
    _do_register_workflow_webhook,
)

log = structlog.get_logger("app.routers.workflows")


# Base directory for bundled playbooks — used when resolving `extends:` at
# install time.  Community submissions pass base_dir=None to block extends.
_PLAYBOOKS_BASE_DIR = pathlib.Path(__file__).parent.parent.parent / "playbooks"


router = APIRouter(prefix="/workflows", tags=["workflows"])


def _run_compiler(version_id, graph: dict):
    """Compile all blocks in a fresh DB session (background task)."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        artifacts = compile_workflow(graph)
        version = db.query(WorkflowVersion).filter(WorkflowVersion.id == version_id).first()
        if version:
            version.compiled_artifacts = artifacts
            db.commit()
    except Exception as e:
        log.error("compile.background_failed", error=str(e))
    finally:
        db.close()


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.view")),
    project_id: str | None = None,
):
    # ponytail: defense in depth — get_workspace_id validates membership on the
    # Clerk path, but not every entry point (machine tokens, test overrides).
    # Re-check here for user identities so a cross-tenant workspace_id header
    # cannot list another workspace's workflows.
    if user_id and user_id != "dev":
        _assert_workspace_member(db, workspace_id, user_id)
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    # Resolve the correct workspace from the project when the active workspace cookie
    # doesn't match the project's workspace (e.g. user navigated across workspace contexts).
    effective_workspace_id = workspace_id
    if project_id:
        from app.models.project import Project
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj and str(proj.workspace_id) != workspace_id:
            proj_ws = str(proj.workspace_id)
            member = db.execute(
                text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
                {"ws": proj_ws, "uid": user_id},
            ).fetchone()
            if member:
                effective_workspace_id = proj_ws

    q = db.query(Workflow).filter(Workflow.workspace_id == effective_workspace_id, Workflow.archived_at.is_(None))
    if project_id:
        q = q.filter(Workflow.project_id == project_id)
    workflows = q.order_by(Workflow.updated_at.desc()).all()

    if not workflows:
        return []

    # Latest run per workflow across ALL versions (not just current) so editing
    # a workflow doesn't make it appear as "never run".
    from sqlalchemy import func
    workflow_uuids = [wf.id for wf in workflows]
    last_run_by_workflow: dict[str, Run] = {}
    if workflow_uuids:
        rn_col = func.row_number().over(
            partition_by=WorkflowVersion.workflow_id,
            order_by=Run.created_at.desc(),
        ).label("rn")
        subq = (
            db.query(
                WorkflowVersion.workflow_id,
                Run.id.label("run_id"),
                Run.status,
                Run.created_at,
                rn_col,
            )
            .join(Run, Run.workflow_version_id == WorkflowVersion.id)
            .filter(WorkflowVersion.workflow_id.in_(workflow_uuids))
            .subquery()
        )
        rows = db.query(subq).filter(subq.c.rn == 1).all()
        for row in rows:
            last_run_by_workflow[str(row.workflow_id)] = row

    # Batch-fetch project names
    from app.models.project import Project as _ListProject
    project_ids = {wf.project_id for wf in workflows if wf.project_id}
    project_names: dict[str, str] = {}
    if project_ids:
        for proj in db.query(_ListProject).filter(_ListProject.id.in_(project_ids)).all():
            project_names[str(proj.id)] = proj.name

    results = []
    for wf in workflows:
        out = WorkflowOut.model_validate(wf)
        last_run = last_run_by_workflow.get(str(wf.id))
        if last_run:
            out.last_run_status = last_run.status
            out.last_run_at = last_run.created_at
        if wf.project_id:
            out.project_name = project_names.get(str(wf.project_id))
        results.append(out)
    return results


FRIENDLY_NAMES_SERVER = {
    "autopilot_full":     "Autopilot Full",
    "autopilot_approved": "Autopilot + Approval",
    "pr_reviewer":        "PR Reviewer",
    "issue_triage":       "Issue Triage",
    "release_notes":      "Release Notes",
    "ci_notify":          "CI Failure Alert",
    "incident_responder": "Incident Responder",
    "dependency_updater": "Dependency Updater",
    "copilot_reviewer":   "Copilot / AI PR Reviewer",
    "smoke_test":             "Smoke Test",
    "thirdparty_autopilot_fix": "Third-Party Autopilot Fix",
}


def _stamp(workflow) -> None:
    """Set transient fields required by WorkflowDetailOut before returning."""
    if not hasattr(workflow, "webhook_error") or workflow.webhook_error is None:  # type: ignore[attr-defined]
        workflow.webhook_error = None  # type: ignore[attr-defined]
    workflow.github_webhook = (workflow.playbook_slug or "") in _GITHUB_WEBHOOK_EVENTS  # type: ignore[attr-defined]


@router.post("", response_model=WorkflowDetailOut, status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _: str = Depends(require_permission("platform.workflows.edit"))):
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    import pathlib

    graph_data = body.graph.model_dump()

    # Backward-compat shim: legacy clients send body.repo as a top-level field.
    # New flow treats `repo` as a normal input declared in the playbook YAML.
    if getattr(body, "repo", None) and "repo" not in (body.inputs or {}):
        if body.inputs is None:
            body.inputs = {}
        body.inputs["repo"] = body.repo

    if body.template and body.template in _TEMPLATE_PLAYBOOKS:
        playbook_file = _TEMPLATE_PLAYBOOKS[body.template]
        playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / playbook_file
        if playbook_path.exists():
            dsl_text = playbook_path.read_text()
            # Substitute {{inputs.xxx}} with user-supplied values, falling back to
            # YAML-declared defaults. Critically, an empty-string user input also
            # falls back to default — otherwise the install modal's empty fields
            # write "" into the YAML and brain blocks lose their model selector.
            import yaml as _yaml
            raw = _yaml.safe_load(dsl_text) or {}
            declared = raw.get("inputs", {})
            user_inputs = body.inputs or {}
            resolved = {}
            for k, v in declared.items():
                supplied = user_inputs.get(k)
                if supplied in (None, ""):
                    supplied = v.get("default", "")
                resolved[k] = str(supplied) if supplied is not None else ""
            for key, val in resolved.items():
                dsl_text = dsl_text.replace(f"{{{{inputs.{key}}}}}", val)
            # Final guard: any {{inputs.X}} left after substitution is a HARD
            # error — the install modal failed to collect a required value or
            # the playbook YAML is missing a default. Either way we refuse to
            # write a broken workflow to the canvas. The frontend shows the
            # 422 with the list of missing keys and re-prompts the user.
            import re as _re2
            leftover = sorted(set(_re2.findall(r"\{\{inputs\.([a-zA-Z_][a-zA-Z0-9_]*)\}\}", dsl_text)))
            if leftover:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "error": "missing_required_inputs",
                        "template": body.template,
                        "missing": leftover,
                        "message": (
                            f"Cannot install {body.template} — required input(s) "
                            f"not supplied: {', '.join(leftover)}. "
                            "Fill them in the install modal or add a default to the playbook YAML."
                        ),
                    },
                )
            try:
                dsl = load_workflow_yaml(dsl_text, base_dir=_PLAYBOOKS_BASE_DIR)
                graph_data = yaml_to_graph(dsl)
            except Exception as _yaml_err:
                log.error("workflow.yaml_parse_failed", template=body.template, error=str(_yaml_err))
                raise HTTPException(status_code=422, detail=f"Template parse error: {_yaml_err}")

    # Resolve environment: use provided, else find/create Default
    from app.models.environment import Environment
    if body.environment_id:
        resolved_env = db.query(Environment).filter(
            Environment.id == body.environment_id,
            Environment.workspace_id == workspace_id,
        ).first()
    else:
        resolved_env = None
    if not resolved_env:
        resolved_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
            Environment.name == "Default",
        ).first()
    if not resolved_env:
        resolved_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
        ).first()
    if not resolved_env:
        resolved_env = Environment(workspace_id=workspace_id, name="Default")
        db.add(resolved_env)
        db.flush()
    default_env = resolved_env

    # Resolve project_id: use provided, else fall back to workspace's default project
    project_id = body.project_id
    if not project_id:
        from sqlalchemy import text as _text
        row = db.execute(
            _text("SELECT id FROM projects WHERE workspace_id = :ws ORDER BY created_at ASC LIMIT 1"),
            {"ws": workspace_id},
        ).fetchone()
        if row:
            project_id = row.id

    workflow = Workflow(
        workspace_id=workspace_id,
        project_id=project_id,
        name=body.name,
        environment_id=default_env.id,
        playbook_slug=body.template or None,
    )
    db.add(workflow)
    db.flush()

    # Auto-prefix workflow name when installed from a playbook with the
    # default name unchanged. Format: Agent-<playbook_slug>-<8 hex> mirrors
    # the per-workflow webhook URL slug suffix at line ~188 — one formula
    # for name + slug + webhook URL.
    if body.template:
        default_name = body.template.replace("_", " ").title()
        if (body.name or "").strip() == default_name:
            workflow.name = f"Agent-{body.template}-{workflow.id.hex[:8]}"

    version = WorkflowVersion(workflow_id=workflow.id, graph=graph_data)
    db.add(version)
    db.flush()

    workflow.current_version_id = version.id
    db.commit()

    # Derive denormalized columns from trigger node config — single source of truth is the graph.
    # Template substitution (above) has already resolved {{inputs.repo}} → trigger.config.repo_allowlist.
    nodes = graph_data.get("nodes", [])
    trigger_node = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
    if trigger_node:
        cfg = trigger_node.get("data", {}).get("config", {}) or {}
        # Primary: substituted graph. Defensive fallback: body.inputs.repo, then legacy body.repo.
        allowlist_raw = cfg.get("repo_allowlist") or (body.inputs or {}).get("repo") or getattr(body, "repo", None) or ""
        first_repo = next((r.strip() for r in str(allowlist_raw).split(",") if r.strip()), None)
        if first_repo:
            workflow.github_hook_repo = first_repo
            # Always reflect into the graph so canvas + webhook stay in sync.
            # Covers: substitution skipped, leftover template literal, or repo from body fallback.
            if cfg.get("repo_allowlist") != first_repo:
                cfg["repo_allowlist"] = first_repo
                trigger_node["data"]["config"] = cfg
                from sqlalchemy.orm.attributes import flag_modified as _flag_repo
                version.graph = graph_data
                _flag_repo(version, "graph")
        labels_raw = cfg.get("labels") or []
        label = labels_raw[0].strip() if labels_raw else None
        if label:
            workflow.github_hook_label = label
    db.commit()

    # Webhook registration is now explicit — user clicks "Activate" on the trigger block.
    # POST /workflows/{id}/webhook does the registration when the user is ready.
    db.refresh(workflow)
    _stamp(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), user_id: str = Depends(get_user_id), _: str = Depends(require_permission("platform.workflows.view"))):
    if user_id and user_id != "dev":
        _assert_workspace_member(db, workspace_id, user_id)
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _stamp(workflow)
    if workflow.project_id:
        from app.models.project import Project as _Proj
        proj = db.query(_Proj).filter(_Proj.id == workflow.project_id).first()
        if proj:
            workflow.project_slug = proj.slug  # type: ignore[attr-defined]
            workflow.project_name = proj.name  # type: ignore[attr-defined]
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowDetailOut)
def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    # SELECT FOR UPDATE — serialise concurrent saves on the same workflow so two
    # editors can't both read, both create a WorkflowVersion, and silently
    # discard each other's changes.  The second writer blocks until the first
    # commits, then reads the refreshed row and applies its edit on top.
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id, Workflow.workspace_id == workspace_id
    ).with_for_update().first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if body.name:
        workflow.name = body.name

    if body.guard_enabled is not None:
        workflow.guard_enabled = body.guard_enabled
    if body.agent_identity_required is not None:
        workflow.agent_identity_required = body.agent_identity_required
    if body.runtime_persona is not None:
        workflow.runtime_persona = (body.runtime_persona or None)  # empty string → NULL (inherit)

    # #2170 — pin a published Gateway profile. Reject unpublished drafts
    # (active_revision_id IS NULL) and cross-workspace ids at the boundary
    # so brain_block never has to reason about either at runtime.
    if "gateway_profile_id" in body.model_fields_set:
        if body.gateway_profile_id is None:
            workflow.gateway_profile_id = None
        else:
            from app.models.gateway_profile import GatewayProfile as _GP
            prof = db.query(_GP).filter(
                _GP.id == body.gateway_profile_id,
                _GP.workspace_id == workspace_id,
            ).first()
            if not prof:
                raise HTTPException(status_code=404, detail="Gateway profile not found in this workspace")
            if prof.active_revision_id is None:
                raise HTTPException(status_code=400, detail="Gateway profile has no published revision")
            workflow.gateway_profile_id = prof.id

    if body.graph is not None:
        graph_dict = body.graph.model_dump()
        version = WorkflowVersion(workflow_id=workflow.id, graph=graph_dict)
        db.add(version)
        db.flush()
        workflow.current_version_id = version.id

        # Keep github_hook_repo and github_hook_label in sync with trigger config.
        # Also normalize: 1 autopilot per repo. If client sent an array, take the first
        # and write it back as a single string so canvas + downstream stay consistent.
        nodes = graph_dict.get("nodes", [])
        trigger_node = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
        if trigger_node:
            cfg = trigger_node.get("data", {}).setdefault("config", {})
            allowlist_val = cfg.get("repo_allowlist") or ""
            if isinstance(allowlist_val, list):
                allowlist_val = allowlist_val[0] if allowlist_val else ""
                cfg["repo_allowlist"] = allowlist_val
            allowlist_raw = str(allowlist_val)
            first_repo = next((r.strip() for r in allowlist_raw.split(",") if r.strip()), None)
            if first_repo and first_repo != workflow.github_hook_repo:
                workflow.github_hook_repo = first_repo
            # labels is a list in the graph config (e.g. ["autopilot-ready"])
            labels_raw = cfg.get("labels") or []
            label = labels_raw[0].strip() if labels_raw else None
            if label != workflow.github_hook_label:
                workflow.github_hook_label = label

        db.commit()
        db.refresh(workflow)

        # Compile in background — doesn't block the save response
        background_tasks.add_task(_run_compiler, version.id, graph_dict)
        _stamp(workflow)
        return workflow

    db.commit()
    db.refresh(workflow)
    # WorkflowUpdate has no ``template`` field — reading it here was a
    # long-standing 500 on every settings-only save (reviewer flagged
    # against #2181). This endpoint is UPDATE, not create; log the
    # settings-changed audit instead of the template-carrying create
    # audit that never made sense here.
    audit(db, workspace_id, "workflow.settings.updated",
          resource_type="workflow", resource_id=str(workflow.id),
          metadata={"name": workflow.name})
    _stamp(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Deregister git webhook only if no sibling workflow shares this hook_id.
    if workflow.github_hook_id and workflow.github_hook_repo:
        try:
            from app.routers.credentials import _git_token
            token, provider = _git_token(str(workspace_id), db)
            siblings = db.query(Workflow).filter(
                Workflow.workspace_id == workflow.workspace_id,
                Workflow.github_hook_repo == workflow.github_hook_repo,
                Workflow.github_hook_id == workflow.github_hook_id,
                Workflow.id != workflow.id,
                Workflow.archived_at.is_(None),
            ).count()
            if siblings == 0:
                _deregister_git_webhook(token, workflow.github_hook_repo, workflow.github_hook_id, provider=provider)
            else:
                log.info("webhook.delete_skipped_shared", workflow_id=str(workflow_id), siblings=siblings)
        except Exception as e:
            log.warning("webhook.deregistration_skipped", workflow_id=str(workflow_id), error=str(e))

    from datetime import datetime, timezone as _tz
    workflow.archived_at = datetime.now(_tz.utc)
    db.commit()
    audit(db, workspace_id, "workflow.archived",
          resource_type="workflow", resource_id=str(workflow_id))


@router.post("/{workflow_id}/webhook", response_model=WorkflowDetailOut)
def register_workflow_webhook(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Explicitly register (or re-register) the GitHub webhook for this workflow."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.github_hook_repo:
        # Try to recover from trigger node config (handles workflows installed before sync fix)
        if workflow.current_version:
            nodes = workflow.current_version.graph.get("nodes", [])
            trigger = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
            if trigger:
                raw = trigger.get("data", {}).get("config", {}).get("repo_allowlist") or ""
                first = next((r.strip() for r in str(raw).split(",") if r.strip()), None)
                if first:
                    workflow.github_hook_repo = first
                    db.commit()
        if not workflow.github_hook_repo:
            raise HTTPException(status_code=400, detail="No repository configured — set repo_allowlist in the trigger block first")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no version — save the canvas first")

    # Single source of truth: _do_register_workflow_webhook helper.
    # It handles token fetch, GitHub-side dedup (via /hooks GET), POST if new,
    # secret encryption, graph writeback. No DB-level dedup that copies stale hook_ids.
    err = _do_register_workflow_webhook(workflow, str(workspace_id), db)
    if err:
        raise HTTPException(status_code=502, detail=err)
    db.refresh(workflow)
    audit(db, workspace_id, "workflow.webhook_registered",
          resource_type="workflow", resource_id=str(workflow_id),
          metadata={"repo": workflow.github_hook_repo})
    _stamp(workflow)
    return workflow


@router.delete("/{workflow_id}/webhook", status_code=204)
def deregister_workflow_webhook(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Deregister the GitHub webhook for this workflow."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.github_hook_id:
        raise HTTPException(status_code=400, detail="No webhook registered")

    try:
        from app.routers.credentials import _git_token
        token, provider = _git_token(str(workspace_id), db, str(workflow.environment_id) if workflow.environment_id else None)

        # Only delete from GitHub if no other workflow in this workspace shares the hook
        siblings = db.query(Workflow).filter(
            Workflow.workspace_id == workspace_id,
            Workflow.github_hook_repo == workflow.github_hook_repo,
            Workflow.github_hook_id == workflow.github_hook_id,
            Workflow.id != workflow_id,
        ).count()

        if siblings == 0:
            _deregister_git_webhook(token, workflow.github_hook_repo or "", workflow.github_hook_id, provider=provider)
        else:
            log.info("webhook.deregister_skipped_shared", workflow_id=str(workflow_id), siblings=siblings)
    except Exception as e:
        log.warning("webhook.deregistration_error", workflow_id=str(workflow_id), error=str(e))

    workflow.github_hook_id = None
    db.commit()
    audit(db, workspace_id, "workflow.webhook_deregistered",
          resource_type="workflow", resource_id=str(workflow_id),
          metadata={"repo": workflow.github_hook_repo})


class BlockCompileRequest(BaseModel):
    description: str
    label: str = ""
    type: str = "tool"
    integration: str | None = None
    isAgentic: bool = False


@router.post("/{workflow_id}/blocks/{block_id}/compile/stream")
def stream_block_compile(
    workflow_id: UUID,
    block_id: str,
    body: BlockCompileRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Stream the compiled prompt for a single block using the current editor state."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    block = {
        "id": block_id,
        "data": {
            "type": body.type,
            "label": body.label,
            "description": body.description,
            "integration": body.integration,
            "isAgentic": body.isAgentic,
        }
    }
    return StreamingResponse(
        stream_compile_block(block),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
