import logging
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id
from app.core.database import get_db

log = logging.getLogger(__name__)
from app.dsl import (
    Workflow as DSLWorkflow,
    WorkflowValidationError,
    graph_to_workflow,
    load_workflow_yaml,
    workflow_to_yaml,
    yaml_filename_for,
    yaml_to_graph,
)
from app.models.run import Run, RunEvent
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


_TEMPLATE_PLAYBOOKS = {
    "autopilot_quick":    "autopilot-quick.yaml",
    "autopilot_full":     "autopilot.yaml",
    "autopilot_approved": "autopilot-approved.yaml",
    "pr_reviewer":        "pr-reviewer.yaml",
    "ci_notify":          "ci-notify.yaml",
    "incident_responder": "incident-responder.yaml",
    "dependency_updater": "dependency-updater.yaml",
    "release_notes":      "release-notes.yaml",
    "issue_triage":       "issue-triage.yaml",
    "copilot_reviewer":   "copilot-reviewer.yaml",
}

_PLAYBOOK_META = {
    "autopilot_quick":    {"icon": "⚡", "tags": ["github", "code"],        "featured": True,  "description": "GitHub issue labeled → implement fix → open PR. No test step — CI runs tests on the PR."},
    "autopilot_full":     {"icon": "🤖", "tags": ["github", "code"],        "featured": True,  "description": "GitHub issue labeled → implement fix → run tests with retry → open PR."},
    "autopilot_approved": {"icon": "✋", "tags": ["github", "code", "approval"], "featured": True, "description": "Implement fix → run tests → human approves in Slack → open PR. Nothing ships without a gate."},
    "pr_reviewer":        {"icon": "🔍", "tags": ["github", "code-review"], "featured": True,  "description": "Any PR opened → AI reviews the diff for bugs, security issues, and style → posts a review comment."},
    "issue_triage":       {"icon": "🏷",  "tags": ["github", "ops"],         "featured": True,  "description": "New issue opened → AI classifies type and priority → adds labels → posts a clarifying comment if vague."},
    "release_notes":      {"icon": "📝", "tags": ["github", "notifications"],"featured": False, "description": "Git tag pushed → AI reads merged PRs → groups by type → writes CHANGELOG entry → posts to Slack."},
    "ci_notify":          {"icon": "🚨", "tags": ["github", "notifications"],"featured": False, "description": "CI build fails → AI diagnoses the failed step → posts root cause and suggested fix to Slack."},
    "incident_responder": {"icon": "🔥", "tags": ["ops", "notifications"],   "featured": False, "description": "Alert fires → AI correlates recent commits and deploys → posts root cause hypothesis to #incidents."},
    "dependency_updater": {"icon": "📦", "tags": ["github", "ops"],          "featured": False, "description": "Weekly cron → AI scans for outdated deps → bumps patch/minor versions → opens a single clean PR."},
    "copilot_reviewer":   {"icon": "🤖", "tags": ["github", "code-review", "approval"], "featured": True, "description": "PR opened by Copilot/Cursor/Claude Code → AI reviews the diff → human approves before merge. The orchestration layer above your AI coding tool."},
}


# Templates that need a GitHub webhook registered — maps slug → GitHub event list
_GITHUB_WEBHOOK_EVENTS: dict[str, list[str]] = {
    "pr_reviewer":        ["pull_request"],
    "copilot_reviewer":   ["pull_request"],
    "issue_triage":       ["issues"],
    "ci_notify":          ["workflow_run"],
    "release_notes":      ["create"],
    "autopilot_quick":    ["issues"],
    "autopilot_full":     ["issues"],
    "autopilot_approved": ["issues"],
}


def _register_github_webhook(token: str, repo: str, workflow_id: str, events: list[str]) -> str | None:
    """Register a webhook on owner/repo and return the hook_id, or None on failure."""
    import httpx
    from app.core.config import settings
    owner, repo_name = repo.split("/", 1)
    webhook_url = f"{settings.api_base_url}/webhooks/inbound/{workflow_id}"
    try:
        r = httpx.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/hooks",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            json={
                "name": "web",
                "active": True,
                "events": events,
                "config": {"url": webhook_url, "content_type": "json"},
            },
            timeout=10,
        )
        if r.status_code == 201:
            return str(r.json()["id"])
        log.warning("GitHub webhook registration returned %s: %s", r.status_code, r.text[:200])
    except Exception as e:
        log.warning("GitHub webhook registration failed: %s", e)
    return None


def _deregister_github_webhook(token: str, repo: str, hook_id: str) -> None:
    """Delete a previously registered webhook. Best-effort — never raises."""
    import httpx
    owner, repo_name = repo.split("/", 1)
    try:
        httpx.delete(
            f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=10,
        )
    except Exception as e:
        log.warning("GitHub webhook deregistration failed: %s", e)


@router.get("/playbooks")
def list_playbooks():
    return [
        {
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "icon": _PLAYBOOK_META[slug]["icon"],
            "description": _PLAYBOOK_META[slug]["description"],
            "tags": _PLAYBOOK_META[slug]["tags"],
            "featured": _PLAYBOOK_META[slug]["featured"],
        }
        for slug in _TEMPLATE_PLAYBOOKS
        if slug in _PLAYBOOK_META
    ]


@router.post("", response_model=WorkflowDetailOut, status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    import pathlib

    graph_data = body.graph.model_dump()

    if body.template and body.template in _TEMPLATE_PLAYBOOKS:
        playbook_file = _TEMPLATE_PLAYBOOKS[body.template]
        playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / playbook_file
        if playbook_path.exists():
            dsl_text = playbook_path.read_text()
            try:
                dsl = load_workflow_yaml(dsl_text)
                graph_data = yaml_to_graph(dsl)
            except Exception:
                pass  # fall through to blank graph on parse error

    # Auto-assign to the workspace's Default environment if one exists
    from app.models.environment import Environment
    default_env = db.query(Environment).filter(
        Environment.workspace_id == workspace_id,
        Environment.name == "Default",
    ).first()

    workflow = Workflow(
        workspace_id=workspace_id,
        name=body.name,
        environment_id=default_env.id if default_env else None,
    )
    db.add(workflow)
    db.flush()

    version = WorkflowVersion(workflow_id=workflow.id, graph=graph_data)
    db.add(version)
    db.flush()

    workflow.current_version_id = version.id
    db.commit()

    # Auto-register GitHub webhook if template needs one and repo was provided
    if body.repo and body.template in _GITHUB_WEBHOOK_EVENTS:
        try:
            from app.routers.credentials import _github_token
            token = _github_token(str(workspace_id), db)
            hook_id = _register_github_webhook(
                token, body.repo, str(workflow.id), _GITHUB_WEBHOOK_EVENTS[body.template]
            )
            if hook_id:
                workflow.github_hook_id = hook_id
                workflow.github_hook_repo = body.repo
                db.commit()
        except Exception as e:
            log.warning("Webhook auto-registration skipped: %s", e)

    db.refresh(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id)):
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
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


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Deregister GitHub webhook if one was auto-registered on install
    if workflow.github_hook_id and workflow.github_hook_repo:
        try:
            from app.routers.credentials import _github_token
            token = _github_token(str(workspace_id), db)
            _deregister_github_webhook(token, workflow.github_hook_repo, workflow.github_hook_id)
        except Exception as e:
            log.warning("Webhook deregistration skipped: %s", e)

    from sqlalchemy import text
    db.execute(text("""
        DELETE FROM run_events WHERE run_id IN (
            SELECT r.id FROM runs r
            JOIN workflow_versions wv ON wv.id = r.workflow_version_id
            WHERE wv.workflow_id = :wid
        )
    """), {"wid": str(workflow_id)})
    db.execute(text("DELETE FROM runs WHERE workflow_version_id IN (SELECT id FROM workflow_versions WHERE workflow_id = :wid)"), {"wid": str(workflow_id)})
    # Null out FK before deleting versions to avoid FK violation
    db.execute(text("UPDATE workflows SET current_version_id = NULL WHERE id = :wid"), {"wid": str(workflow_id)})
    db.execute(text("DELETE FROM workflow_versions WHERE workflow_id = :wid"), {"wid": str(workflow_id)})
    db.execute(text("DELETE FROM workflows WHERE id = :wid"), {"wid": str(workflow_id)})
    db.commit()


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
):
    """Stream the compiled prompt for a single block using the current editor state."""
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


class PreflightRequest(BaseModel):
    issue_title: str = ""
    issue_body: str = ""


@router.post("/{workflow_id}/preflight")
def preflight_workflow(
    workflow_id: UUID,
    body: PreflightRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Estimate the turn budget needed before starting a run.
    Makes a single cheap Claude call per agentic brain block — no tools, pure reasoning.
    Returns suggested_max_turns and a per-block breakdown.
    """
    from app.core.config import settings
    import anthropic

    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    graph = workflow.current_version.graph or {}
    nodes = graph.get("nodes", [])
    brain_blocks = [
        n for n in nodes
        if n.get("data", {}).get("type") == "brain"
        and n.get("data", {}).get("isAgentic", False)
    ]

    if not brain_blocks:
        return {"suggested_max_turns": 20, "blocks": [], "total_files": []}

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    block_estimates = []
    all_files: list[str] = []

    for block in brain_blocks:
        data = block.get("data", {})
        label = data.get("label", block.get("id", "?"))
        description = data.get("description", "")

        prompt = (
            f"You are estimating work for an AI coding agent.\n\n"
            f"Issue title: {body.issue_title}\n"
            f"Issue body: {body.issue_body}\n\n"
            f"Brain block task:\n{description}\n\n"
            f"Estimate: how many tool calls (shell commands, file reads, file writes) "
            f"will this block need to complete this task?\n"
            f"Respond with JSON only, no explanation:\n"
            f'{{ "files": ["path/to/file", ...], "estimated_turns": <number>, "reasoning": "<one line>" }}'
        )

        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            import json, re
            text = resp.content[0].text.strip()
            # extract JSON even if wrapped in markdown
            m = re.search(r"\{.*\}", text, re.DOTALL)
            parsed = json.loads(m.group()) if m else {}
            est = int(parsed.get("estimated_turns", 20))
            files = parsed.get("files", [])
            reasoning = parsed.get("reasoning", "")
        except Exception:
            est, files, reasoning = 20, [], ""

        block_estimates.append({
            "block_id": block.get("id"),
            "label": label,
            "estimated_turns": est,
            "files": files,
            "reasoning": reasoning,
        })
        all_files.extend(files)

    total = sum(b["estimated_turns"] for b in block_estimates)
    # add 5 turns buffer for commit/push/PR steps
    suggested = max(total + 5, 20)

    return {
        "suggested_max_turns": suggested,
        "blocks": block_estimates,
        "total_files": list(dict.fromkeys(all_files)),  # deduplicated
    }


@router.post("/{workflow_id}/validate")
def validate_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Pre-flight validation before starting a run.
    Checks: credentials configured, required block fields set, Brain descriptions sufficient.
    Returns {valid: bool, errors: [{block_id, label, message}]}
    """
    import re
    from app.models.integration import Integration
    from app.core.crypto import decrypt

    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    graph = workflow.current_version.graph or {}
    nodes = graph.get("nodes", [])

    # Which integrations are configured?
    cred_rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id
    ).all()
    configured_handles = {row.handle for row in cred_rows if row.encrypted_credentials}

    errors = []

    for node in nodes:
        data = node.get("data", {})
        block_type = data.get("type", "tool")
        label = data.get("label") or node.get("id", "?")
        block_id = node.get("id", "?")
        config = data.get("config") or {}
        integration = data.get("integration", "")

        # ── Trigger blocks ──────────────────────────────────────────────────
        if block_type == "trigger":
            event_type = config.get("event_type", "")
            if event_type in ("github_issue_labeled", "github_issue"):
                if "github" not in configured_handles:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "GitHub credential not configured — connect it in Settings"})
                if not config.get("repo_allowlist"):
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "repo_allowlist is required (e.g. owner/repo)"})
                if not config.get("label"):
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "label is required (e.g. ai_ready)"})

        # ── Brain blocks ─────────────────────────────────────────────────────
        # description IS the system prompt — no separate system_prompt field exists
        elif block_type == "brain":
            description = (data.get("description") or config.get("description") or "").strip()
            if not description:
                errors.append({"block_id": block_id, "label": label,
                                "message": "Description is required for Brain blocks"})

        # ── Tool / cleanup blocks ────────────────────────────────────────────
        elif block_type in ("tool", "cleanup"):
            if not integration:
                errors.append({"block_id": block_id, "label": label,
                                "message": "No integration selected"})
            else:
                # Check the needed credential is configured
                needed = integration.lower().split(":")[0]
                if needed not in configured_handles:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": f"{integration} credential not configured — connect it in Settings"})
                action = config.get("action", "")
                if not action:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": f"No action selected for {integration}"})

        # ── Output blocks ────────────────────────────────────────────────────
        elif block_type == "output":
            via = integration or "slack"
            if via in ("slack", "both"):
                if not config.get("channel"):
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "Slack channel is required (e.g. #general)"})
                if "slack" not in configured_handles:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "Slack credential not configured — connect it in Settings"})
            if via in ("email", "both") and not config.get("to"):
                errors.append({"block_id": block_id, "label": label,
                                "message": "Email address (To) is required"})
            if via == "webhook" and not config.get("webhook_url"):
                errors.append({"block_id": block_id, "label": label,
                                "message": "Webhook URL is required"})

    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/{workflow_id}/estimate")
def estimate_workflow_cost(
    workflow_id: UUID,
    issues: int = 1,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Estimate token usage and cost for this workflow.
    Uses actual historical run data when available; falls back to static estimates.
    ?issues=N multiplies cost by number of matching GitHub issues.
    Pricing: Claude Sonnet 4.6 — $3/1M input, $15/1M output.
    """
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no compiled version")

    version = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == workflow.current_version_id
    ).first()

    graph     = version.graph or {}
    artifacts = version.compiled_artifacts or {}
    nodes     = graph.get("nodes", [])

    # Pricing constants (Claude Sonnet 4.6)
    INPUT_PRICE_PER_TOKEN  = 3.00  / 1_000_000
    OUTPUT_PRICE_PER_TOKEN = 15.00 / 1_000_000
    CHARS_PER_TOKEN        = 4

    # ── Pull historical actuals from past succeeded runs ──────────────────────
    # RunEvent.payload shape for block_completed:
    #   {"output": {"input_tokens": N, "output_tokens": N, "turns": N, "cost_usd": N}}
    past_events = (
        db.query(RunEvent)
        .join(Run, RunEvent.run_id == Run.id)
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .filter(
            WorkflowVersion.workflow_id == workflow_id,
            RunEvent.kind == "block_completed",
            Run.status == "succeeded",
        )
        .all()
    )

    # Build per-block actuals: block_id → {avg_input, avg_output, avg_turns, samples}
    block_actuals: dict[str, dict] = {}
    for ev in past_events:
        bid = ev.block_id
        if not bid:
            continue
        out = (ev.payload or {}).get("output") or {}
        if not isinstance(out, dict):
            continue
        in_tok  = out.get("input_tokens")
        out_tok = out.get("output_tokens")
        turns   = out.get("turns")
        if in_tok is None or out_tok is None:
            continue
        if bid not in block_actuals:
            block_actuals[bid] = {"input": [], "output": [], "turns": []}
        block_actuals[bid]["input"].append(int(in_tok))
        block_actuals[bid]["output"].append(int(out_tok))
        if turns is not None:
            block_actuals[bid]["turns"].append(int(turns))

    def _avg(lst: list[int]) -> int:
        return round(sum(lst) / len(lst)) if lst else 0

    # ── Per-block estimates ───────────────────────────────────────────────────
    blocks: list[dict] = []
    total_input_tokens  = 0
    total_output_tokens = 0
    integrations_used: set[str] = set()
    has_actuals = False

    for node in nodes:
        nid   = node["id"]
        data  = node.get("data", {})
        label = data.get("label", nid)
        btype = data.get("type", "tool")
        art   = artifacts.get(nid, {})
        mode  = art.get("mode", btype)

        system_prompt = art.get("system_prompt", "")
        prompt_tokens = len(system_prompt) // CHARS_PER_TOKEN

        integration = data.get("integration") or (data.get("config") or {}).get("integration")
        if integration:
            integrations_used.add(integration)

        actuals = block_actuals.get(nid)

        if actuals:
            # Use averaged actuals from real runs
            has_actuals = True
            input_tokens  = _avg(actuals["input"])
            output_tokens = _avg(actuals["output"])
            avg_turns     = _avg(actuals["turns"]) if actuals["turns"] else None
            samples       = len(actuals["input"])
            if avg_turns:
                note = f"avg {avg_turns} turns · {samples} run{'s' if samples > 1 else ''}"
            else:
                note = f"avg of {samples} run{'s' if samples > 1 else ''}"

        elif mode == "agentic":
            input_tokens  = (prompt_tokens + 1500) * 5
            output_tokens = 800 * 5
            note = "~5 turns (no history yet)"

        elif mode == "brain":
            input_tokens  = prompt_tokens + 1500
            output_tokens = 500
            note = "single call (no history yet)"

        elif mode in ("trigger", "tool", "output", "cleanup", "memory"):
            input_tokens  = 0
            output_tokens = 0
            note = "no LLM call"

        elif mode == "logic":
            input_tokens  = prompt_tokens + 1500
            output_tokens = 50
            note = "routing only"

        elif mode == "approval":
            input_tokens  = 0
            output_tokens = 0
            note = "human gate — no LLM"

        else:
            input_tokens  = prompt_tokens + 1500
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

    per_run_cost = (total_input_tokens * INPUT_PRICE_PER_TOKEN) + (total_output_tokens * OUTPUT_PRICE_PER_TOKEN)
    issues       = max(1, issues)
    total_cost   = per_run_cost * issues

    return {
        "workflow_id":          str(workflow_id),
        "block_count":          len(nodes),
        "blocks":               blocks,
        "total_input_tokens":   total_input_tokens,
        "total_output_tokens":  total_output_tokens,
        "total_tokens":         total_input_tokens + total_output_tokens,
        "per_run_cost_usd":     round(per_run_cost, 4),
        "issues_count":         issues,
        "total_cost_usd":       round(total_cost, 4),
        "integrations_used":    sorted(integrations_used),
        "model":                "claude-sonnet-4-6",
        "pricing_note":         "$3/1M input · $15/1M output",
        "based_on_actuals":     has_actuals,
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
):
    """
    Replace the workflow definition with the provided YAML.

    Returns the workflow with its new current_version_id. The compiled
    artifacts are produced in the background — the caller doesn't wait.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        dsl = load_workflow_yaml(yaml_text)
    except WorkflowValidationError as e:
        raise HTTPException(status_code=400, detail=f"Invalid workflow YAML: {e}")

    graph_dict = yaml_to_graph(dsl)
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
def get_workflow_yaml(workflow_id: UUID, db: Session = Depends(get_db)):
    """
    Return the YAML source for the workflow's current version.

    Sets ``Content-Disposition`` so curl / browsers / the CLI all save the
    file as ``<projectname>-delegator.yml`` — the same convention the canvas
    suggests and the customer is expected to commit to their repo.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
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
def get_workflow_yaml_filename(workflow_id: UUID, db: Session = Depends(get_db)):
    """
    Return the canonical YAML filename + a suggested ``source_path`` for the
    Settings UI to use as the default when binding the workflow to a repo.
    Keeps the naming convention in one place (``app.dsl.naming``) and lets the
    frontend just read it rather than re-implement the slug.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
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
        dsl = load_workflow_yaml(body.yaml)
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
):
    """Assign or clear the environment scoping for a workflow."""
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


class SyncRequest(BaseModel):
    ref: str | None = None  # branch / tag / sha; default = repo default branch


@router.post("/{workflow_id}/sync")
def sync_workflow(
    workflow_id: UUID,
    body: SyncRequest = Body(default=SyncRequest()),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
):
    """
    Fetch the YAML at ``workflow.source_repo:source_path`` from GitHub,
    validate it, and create a new WorkflowVersion if the content changed.
    No-op when the source matches the current version.
    """
    from app.dsl.sync import SyncError, sync_workflow_from_repo

    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    try:
        result = sync_workflow_from_repo(db=db, workflow=workflow, ref=body.ref)
    except SyncError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # If the sync produced a new version, trigger compilation in the background.
    if result.get("changed") and background_tasks is not None:
        version = db.query(WorkflowVersion).filter(
            WorkflowVersion.id == workflow.current_version_id
        ).first()
        if version:
            background_tasks.add_task(_run_compiler, version.id, version.graph)

    return result
