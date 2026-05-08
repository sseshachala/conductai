from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowCreate, WorkflowUpdate, WorkflowOut, WorkflowDetailOut
from app.compiler.compiler import compile_workflow
from app.compiler.stream import stream_compile_block

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
        import logging
        logging.getLogger(__name__).error("Background compile failed: %s", e)
    finally:
        db.close()


@router.get("", response_model=list[WorkflowOut])
def list_workflows(db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    workflows = db.query(Workflow).filter(
        Workflow.workspace_id == workspace_id
    ).order_by(Workflow.updated_at.desc()).all()

    # Attach last run status to each workflow
    results = []
    for wf in workflows:
        last_run = None
        if wf.current_version_id:
            last_run = db.query(Run).filter(
                Run.workflow_version_id == wf.current_version_id
            ).order_by(Run.created_at.desc()).first()
        out = WorkflowOut.model_validate(wf)
        if last_run:
            out.last_run_status = last_run.status
            out.last_run_at = last_run.created_at
        results.append(out)
    return results


@router.post("", response_model=WorkflowDetailOut, status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    workflow = Workflow(workspace_id=workspace_id, name=body.name)
    db.add(workflow)
    db.flush()

    version = WorkflowVersion(workflow_id=workflow.id, graph=body.graph.model_dump())
    db.add(version)
    db.flush()

    workflow.current_version_id = version.id
    db.commit()
    db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowDetailOut)
def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    if body.name:
        workflow.name = body.name

    if body.graph is not None:
        graph_dict = body.graph.model_dump()
        version = WorkflowVersion(workflow_id=workflow.id, graph=graph_dict)
        db.add(version)
        db.flush()
        workflow.current_version_id = version.id
        db.commit()
        db.refresh(workflow)

        # Compile in background — doesn't block the save response
        background_tasks.add_task(_run_compiler, version.id, graph_dict)
        return workflow

    db.commit()
    db.refresh(workflow)
    return workflow


class BlockCompileRequest(BaseModel):
    description: str
    label: str = ""
    type: str = "tool"
    integration: str | None = None
    isAgentic: bool = False


@router.post("/{workflow_id}/blocks/{block_id}/compile/stream")
def stream_block_compile(workflow_id: UUID, block_id: str, body: BlockCompileRequest):
    """Stream the compiled prompt for a single block using the current editor state."""
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


@router.get("/{workflow_id}/estimate")
def estimate_workflow_cost(workflow_id: UUID, db: Session = Depends(get_db)):
    """
    Estimate token usage and cost for one run of this workflow.
    Uses compiled artifacts (system prompts) to count tokens.
    Pricing: Claude Sonnet 4.6 — $3/1M input, $15/1M output.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no compiled version")

    version = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == workflow.current_version_id
    ).first()

    graph = version.graph or {}
    artifacts = version.compiled_artifacts or {}
    nodes = graph.get("nodes", [])

    # Pricing constants (Claude Sonnet 4.6)
    INPUT_PRICE_PER_TOKEN  = 3.00  / 1_000_000
    OUTPUT_PRICE_PER_TOKEN = 15.00 / 1_000_000
    CHARS_PER_TOKEN = 4  # rough approximation

    # Context grows as blocks run — estimate average context size passed in
    AVG_CONTEXT_TOKENS = 1500

    blocks = []
    total_input_tokens  = 0
    total_output_tokens = 0
    integrations_used: set[str] = set()

    for node in nodes:
        nid   = node["id"]
        data  = node.get("data", {})
        label = data.get("label", nid)
        btype = data.get("type", "tool")
        art   = artifacts.get(nid, {})
        mode  = art.get("mode", btype)

        system_prompt = art.get("system_prompt", "")
        prompt_tokens = len(system_prompt) // CHARS_PER_TOKEN

        integration = data.get("integration") or data.get("config", {}).get("integration")
        if integration:
            integrations_used.add(integration)

        if mode == "agentic":
            # Multi-turn: estimate 5 turns average, each sees full context
            est_turns        = 5
            input_per_turn   = prompt_tokens + AVG_CONTEXT_TOKENS
            output_per_turn  = 800
            input_tokens     = input_per_turn  * est_turns
            output_tokens    = output_per_turn * est_turns
            note = f"~{est_turns} turns estimated"

        elif mode in ("brain",):
            input_tokens  = prompt_tokens + AVG_CONTEXT_TOKENS
            output_tokens = 500
            note = "single call"

        elif mode in ("trigger", "tool", "output", "cleanup", "memory"):
            # No LLM call — just API calls
            input_tokens  = 0
            output_tokens = 0
            note = "no LLM call"

        elif mode == "logic":
            input_tokens  = prompt_tokens + AVG_CONTEXT_TOKENS
            output_tokens = 50
            note = "routing only"

        elif mode == "approval":
            input_tokens  = 0
            output_tokens = 0
            note = "human gate — no LLM"

        else:
            input_tokens  = prompt_tokens + AVG_CONTEXT_TOKENS
            output_tokens = 200
            note = ""

        cost = (input_tokens * INPUT_PRICE_PER_TOKEN) + (output_tokens * OUTPUT_PRICE_PER_TOKEN)

        blocks.append({
            "block_id":      nid,
            "label":         label,
            "type":          btype,
            "mode":          mode,
            "integration":   integration,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      round(cost, 6),
            "note":          note,
        })

        total_input_tokens  += input_tokens
        total_output_tokens += output_tokens

    total_cost = (total_input_tokens * INPUT_PRICE_PER_TOKEN) + (total_output_tokens * OUTPUT_PRICE_PER_TOKEN)

    return {
        "workflow_id":          str(workflow_id),
        "block_count":          len(nodes),
        "blocks":               blocks,
        "total_input_tokens":   total_input_tokens,
        "total_output_tokens":  total_output_tokens,
        "total_tokens":         total_input_tokens + total_output_tokens,
        "total_cost_usd":       round(total_cost, 4),
        "integrations_used":    sorted(integrations_used),
        "model":                "claude-sonnet-4-6",
        "pricing_note":         "$3/1M input · $15/1M output",
    }


@router.post("/{workflow_id}/compile", response_model=WorkflowDetailOut)
def compile_workflow_now(workflow_id: UUID, db: Session = Depends(get_db)):
    """Explicitly trigger compilation for the current version."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="No version to compile")

    version = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == workflow.current_version_id
    ).first()

    artifacts = compile_workflow(version.graph)
    version.compiled_artifacts = artifacts
    db.commit()
    db.refresh(workflow)
    return workflow
