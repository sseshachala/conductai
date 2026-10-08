"""Workflow YAML source-of-truth + settings endpoints (split from workflows.py).

Third link of the route-registration chain (see workflows_crud).
"""
from typing import Optional
from uuid import UUID
from fastapi import Body, Depends, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.dsl import (
    WorkflowValidationError,
    graph_to_workflow,
    load_workflow_yaml,
    workflow_to_yaml,
    yaml_filename_for,
    yaml_to_graph,
    carry_annotations,
)
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowDetailOut
from app.runtime.input_contract import validate_required_inputs
from app.routers.workflows_crud import (
    _PLAYBOOKS_BASE_DIR,
    _run_compiler,
)
from app.routers.workflows_validation import router


# ── YAML source-of-truth endpoints ────────────────────────────────────────────
#
# YAML is the authoritative workflow definition. PUT accepts a YAML body,
# validates it via the DSL, derives the {nodes, edges} graph, stores both,
# and triggers compilation. GET returns the YAML so the canvas (or any
# external tool) can round-trip the source.

@router.put("/{workflow_id}/yaml", response_model=WorkflowDetailOut)
def update_workflow_yaml(
    workflow_id: UUID,
    background_tasks: BackgroundTasks,
    yaml_text: str = Body(..., media_type="application/x-yaml"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """
    Replace the workflow definition with the provided YAML.

    Returns the workflow with its new current_version_id. The compiled
    artifacts are produced in the background — the caller doesn't wait.
    """
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    # SELECT FOR UPDATE — same serialisation as the graph PUT endpoint.
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id, Workflow.workspace_id == workspace_id
    ).with_for_update().first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        dsl = load_workflow_yaml(yaml_text, base_dir=_PLAYBOOKS_BASE_DIR)
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid workflow YAML: {e}")

    previous = db.query(WorkflowVersion).filter(WorkflowVersion.id == workflow.current_version_id).first()
    graph_dict = carry_annotations(yaml_to_graph(dsl), previous.graph if previous else None)
    version = WorkflowVersion(
        workflow_id=workflow.id,
        yaml_source=yaml_text,
        graph=graph_dict,
    )
    db.add(version)
    db.flush()
    workflow.current_version_id = version.id
    if dsl.name and not workflow.name:
        workflow.name = dsl.name
    db.commit()
    db.refresh(workflow)

    background_tasks.add_task(_run_compiler, version.id, graph_dict)
    return workflow


@router.get("/{workflow_id}/yaml", response_class=PlainTextResponse)
def get_workflow_yaml(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """
    Return the YAML source for the workflow's current version.

    Sets ``Content-Disposition`` so curl / browsers / the CLI all save the
    file as ``<projectname>-delegator.yml`` — the same convention the canvas
    suggests and the customer is expected to commit to their repo.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.current_version_id:
        raise HTTPException(status_code=404, detail="Workflow has no version yet")

    version = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == workflow.current_version_id
    ).first()

    # Prefer the stored YAML. If a workflow predates the DSL (graph-only),
    # we don't try to reverse-engineer YAML from the JSON graph yet — that's
    # a phase-2 migration tool.
    if not (version and version.yaml_source):
        raise HTTPException(
            status_code=404,
            detail="This workflow has no YAML source — it predates the DSL migration",
        )

    filename = yaml_filename_for(workflow.name)
    return PlainTextResponse(
        content=version.yaml_source,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{workflow_id}/yaml/filename")
def get_workflow_yaml_filename(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """
    Return the canonical YAML filename + a suggested ``source_path`` for the
    Settings UI to use as the default when binding the workflow to a repo.
    Keeps the naming convention in one place (``app.dsl.naming``) and lets the
    frontend just read it rather than re-implement the slug.
    """
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    filename = yaml_filename_for(workflow.name)
    return {
        "filename": filename,
        "suggested_source_path": filename,
    }


class YamlValidateRequest(BaseModel):
    yaml: str


@router.post("/yaml/validate")
def validate_workflow_yaml(body: YamlValidateRequest):
    """
    Dry-run validation for the canvas / editor — no DB writes. Returns the
    derived graph on success so the canvas can render it immediately.
    """
    try:
        dsl = load_workflow_yaml(body.yaml, base_dir=_PLAYBOOKS_BASE_DIR)
    except WorkflowValidationError as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "name": dsl.name,
        "block_count": len(dsl.blocks) + len(dsl.cleanup),
        "graph": yaml_to_graph(dsl),
    }


class GraphToYamlRequest(BaseModel):
    """Canvas-shaped graph plus the workflow's metadata."""
    id: str | None = None
    workspace_id: str | None = None
    name: str
    description: str | None = None
    graph: dict  # { nodes: [...], edges: [...] }


@router.post("/yaml/from-graph")
def workflow_yaml_from_graph(body: GraphToYamlRequest):
    """
    Convert a React Flow ``{nodes, edges}`` payload into the canonical YAML.
    Used by the canvas to serialize its state without reimplementing the DSL
    schema in TypeScript.
    """
    try:
        dsl = graph_to_workflow(body.graph, name=body.name, description=body.description)
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid graph: {e}")
    dsl.id = body.id
    dsl.workspace_id = body.workspace_id
    return {"yaml": workflow_to_yaml(dsl)}


# ── Repo source binding + sync ────────────────────────────────────────────────


class WorkflowEnvironmentRequest(BaseModel):
    """Assign (or clear) an environment on a workflow."""
    environment_id: str | None = None  # UUID string or null to clear


@router.patch("/{workflow_id}/environment")
def set_workflow_environment(
    workflow_id: UUID,
    body: WorkflowEnvironmentRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Assign or clear the environment scoping for a workflow."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    workflow.environment_id = body.environment_id or None
    db.commit()
    db.refresh(workflow)
    return {"id": str(workflow.id), "environment_id": str(workflow.environment_id) if workflow.environment_id else None}


class WorkflowTurnSettingsRequest(BaseModel):
    default_max_turns: Optional[int] = None


@router.patch("/{workflow_id}/turn-settings")
def update_turn_settings(
    workflow_id: UUID,
    body: WorkflowTurnSettingsRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Persist a default turn budget override for this workflow."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.default_max_turns = body.default_max_turns
    db.commit()
    return {"id": str(workflow.id), "default_max_turns": workflow.default_max_turns}


class WorkflowSourceRequest(BaseModel):
    """Bind a workflow to a YAML file in a customer's GitHub repo."""
    source_repo: str | None = None   # "owner/repo" — pass null to unset
    source_path: str | None = None   # path within repo, e.g. "delegator.yml"


@router.put("/{workflow_id}/source", response_model=WorkflowDetailOut)
def update_workflow_source(
    workflow_id: UUID,
    body: WorkflowSourceRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Configure (or clear) the GitHub-repo source binding for a workflow."""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.source_repo = body.source_repo or None
    workflow.source_path = body.source_path or None
    db.commit()
    db.refresh(workflow)
    return workflow


@router.post("/{workflow_id}/validate-inputs")
def validate_workflow_inputs(
    workflow_id: UUID,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """Dry-run input validation for pre-run modal (#713/#734).
    Returns {inputs_spec, missing} so the client can prompt only for missing required-at-run inputs.
    """
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")
    inputs_spec = (workflow.current_version.graph or {}).get("inputs_spec") or {}
    inputs = payload.get("inputs") or {}
    missing = validate_required_inputs(inputs_spec, inputs, phase=payload.get("phase", "run"))
    return {"inputs_spec": inputs_spec, "missing": missing}
