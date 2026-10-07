"""Workflow preflight / validate / estimate / compile endpoints (split from workflows.py).

Second link of the route-registration chain (see workflows_crud).
"""
from uuid import UUID
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_permission
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.workflow import WorkflowDetailOut
from app.compiler.compiler import compile_workflow
from app.runtime.model_router import resolve_for_workspace as resolve_model
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates, pricing_note
from app.routers.workflows_preflight import _estimate_turns_for_graph
from app.routers.workflows_crud import (
    _stamp,
    router,
)


class PreflightRequest(BaseModel):
    issue_title: str = ""
    issue_body: str = ""
    run_inputs: dict = {}


@router.post("/{workflow_id}/preflight")
def preflight_workflow(
    workflow_id: UUID,
    body: PreflightRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """
    Estimate the turn budget needed before starting a run.
    Makes a single cheap Claude call per agentic brain block — no tools, pure reasoning.
    Returns suggested_max_turns and a per-block breakdown.
    """
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")


    graph = workflow.current_version.graph or {}
    # min_turns: max of YAML-declared min_turns input default and workflow-level DB override
    yaml_min = 0
    import yaml as _yaml
    if workflow.current_version.yaml_source:
        try:
            raw = _yaml.safe_load(workflow.current_version.yaml_source) or {}
            yaml_min = int((raw.get("inputs", {}).get("min_turns", {}) or {}).get("default", 0))
        except Exception:
            pass
    min_turns = max(yaml_min, workflow.default_max_turns or 0)
    result = _estimate_turns_for_graph(graph, body.issue_title, body.issue_body, min_turns, workspace_id, db, workflow_id=str(workflow_id))
    result["min_turns"] = min_turns
    return result


@router.post("/{workflow_id}/validate")
def validate_workflow(
    workflow_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """
    Pre-flight validation before starting a run.
    Checks: credentials configured, required block fields set, Brain descriptions sufficient.
    Returns {valid: bool, errors: [{block_id, label, message}]}
    """
    from app.models.integration import Integration
    from app.core.crypto import decrypt

    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    graph = workflow.current_version.graph or {}
    nodes = graph.get("nodes", [])

    # Which integrations are configured?
    # Scope strictly to the selected environment — no Default fallback.
    # The validator must reflect exactly what the selected env provides so gaps
    # are surfaced here rather than silently papered over at runtime.
    from app.models.environment import Environment as _ValidatorEnv
    env_id = workflow.environment_id
    if env_id:
        cred_rows = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == env_id,
        ).all()
    else:
        # No environment assigned — check Default
        default_env = db.query(_ValidatorEnv).filter(
            _ValidatorEnv.workspace_id == workspace_id,
            _ValidatorEnv.name == "Default",
        ).first()
        cred_rows = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == default_env.id,
        ).all() if default_env else []

    configured_services = {row.service.lower() for row in cred_rows if row.encrypted_credentials}
    # "git" handle covers GITHUB_TOKEN / GITLAB_TOKEN stored via env-var UI → counts as "github"
    if "git" in configured_services:
        configured_services.add("github")

    # Collect available env var keys (uppercased) for provider credential checks.
    # Handles: env_vars (flat keys), modal (token_id/token_secret), anthropic (api_key).
    available_env_keys: set[str] = set()
    for row in cred_rows:
        if not row.encrypted_credentials:
            continue
        decrypted = decrypt(row.encrypted_credentials) or {}
        if row.handle == "env_vars":
            available_env_keys.update(k.upper() for k in decrypted.keys())
        elif row.handle == "modal":
            if decrypted.get("token_id"):
                available_env_keys.add("MODAL_TOKEN_ID")
            if decrypted.get("token_secret"):
                available_env_keys.add("MODAL_TOKEN_SECRET")
        elif row.handle == "anthropic":
            if decrypted.get("api_key"):
                available_env_keys.add("ANTHROPIC_API_KEY")

    from app.runtime.provider_keys import provider_for_model, provider_key_exists, ENV_VAR

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
                if "github" not in configured_services:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "GitHub credential not configured — connect it in Settings"})
                if not config.get("repo_allowlist"):
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "repo_allowlist is required (e.g. owner/repo)"})
                labels = config.get("labels") or config.get("label")
                if not labels:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "label is required (e.g. ai_ready)"})

        # ── Brain blocks ─────────────────────────────────────────────────────
        # description IS the system prompt — no separate system_prompt field exists
        elif block_type == "brain":
            description = (data.get("description") or config.get("description") or "").strip()
            if not description:
                errors.append({"block_id": block_id, "label": label,
                                "message": "Description is required for Brain blocks"})

            brain_model = data.get("model") or config.get("model") or ""
            brain_provider = provider_for_model(brain_model)
            if not provider_key_exists(brain_provider, available_env_keys):
                errors.append({"block_id": block_id, "label": label,
                                "message": f"{ENV_VAR[brain_provider]} is not set for {brain_provider} model '{brain_model or 'default'}' — add it under Settings → Environments"})

            # Execution provider credential checks
            runs_on = data.get("runs_on") or {}
            provider = runs_on.get("provider") if isinstance(runs_on, dict) else None
            if provider == "modal":
                missing = []
                if "MODAL_TOKEN_ID" not in available_env_keys:
                    missing.append("MODAL_TOKEN_ID")
                if "MODAL_TOKEN_SECRET" not in available_env_keys:
                    missing.append("MODAL_TOKEN_SECRET")
                if missing:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": f"Modal Labs credentials not set — add {' and '.join(missing)} under Settings → Environments"})
            elif provider == "e2b":
                if "E2B_API_KEY" not in available_env_keys:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "E2B_API_KEY is not set — add it under Settings → Environments"})

        # ── Tool / cleanup blocks ────────────────────────────────────────────
        elif block_type in ("tool", "cleanup"):
            if not integration:
                errors.append({"block_id": block_id, "label": label,
                                "message": "No integration selected"})
            else:
                # Check the needed credential is configured
                needed = integration.lower().split(":")[0]
                if needed not in configured_services:
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
                if "slack" not in configured_services:
                    errors.append({"block_id": block_id, "label": label,
                                   "message": "Slack credential not configured — connect it in Settings"})
            if via in ("email", "both") and not config.get("to"):
                errors.append({"block_id": block_id, "label": label,
                                "message": "Email address (To) is required"})
            if via == "webhook" and not config.get("webhook_url"):
                errors.append({"block_id": block_id, "label": label,
                                "message": "Webhook URL is required"})

    # ── Runtime chain checks ────────────────────────────────────────────────
    # These catch auth/config failures that only surface mid-run without this check.
    from sqlalchemy import text as _sql
    from app.core.config import settings as _settings

    # 1. Workspace membership — must be in workspace_users
    if user_id:
        membership = db.execute(
            _sql("SELECT 1 FROM workspace_users WHERE workspace_id::text = :ws AND clerk_user_id = :uid LIMIT 1"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if not membership:
            errors.append({"block_id": "__runtime__", "label": "Auth",
                           "message": "Your account is not a member of this workspace — run `conduct login` to re-authenticate"})

    # 2. Token type — cond_agt_* must be token_type='cli', not 'api'
    raw_auth = request.headers.get("authorization", "")
    if raw_auth.lower().startswith("bearer "):
        raw_tok = raw_auth[7:].strip()
        if raw_tok.startswith("cond_agt_"):
            from app.core.auth import resolve_agent_identity_row
            _ai = resolve_agent_identity_row(raw_tok, db)
            if _ai and getattr(_ai, "token_type", "cli") != "cli":
                errors.append({"block_id": "__runtime__", "label": "Auth",
                               "message": "Agent token type is not 'cli' — run `conduct login` to re-mint"})

    # 3. Credential broker URL — must be a reachable public URL in production
    if _settings.environment != "development" and (
        not _settings.api_base_url or "localhost" in _settings.api_base_url
    ):
        errors.append({"block_id": "__runtime__", "label": "Config",
                       "message": "API_BASE_URL is not set to a public URL — credential broker will fail at runtime"})

    # 4. Guard proxy configured
    if not _settings.conduct_proxy_url:
        errors.append({"block_id": "__runtime__", "label": "Guard Proxy",
                       "message": "conduct_proxy_url is not configured — brain blocks cannot route through Guard"})

    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/{workflow_id}/estimate")
def estimate_workflow_cost(
    workflow_id: UUID,
    issues: int = 1,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """
    Estimate token usage and cost for this workflow.
    Uses actual historical run data when available; falls back to static estimates.
    ?issues=N multiplies cost by number of matching GitHub issues.
    Pricing is resolved from the runtime pricing registry.
    """
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
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

    CHARS_PER_TOKEN        = 4
    pricing_snapshot = freeze_pricing_snapshot()

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
    llm_models_used: set[str] = set()
    llm_pricing_note: str | None = None
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

        provider = None
        model = None
        rates = None
        if mode in ("agentic", "brain", "logic"):
            routing_pref = data.get("routingPreference") or "balanced"
            explicit_model = data.get("model") or None
            explicit_provider = data.get("provider") or None
            provider, model, _ = resolve_model(db, str(workflow.workspace_id), routing_pref, explicit_model, explicit_provider)
            rates, pricing_version = get_model_rates(provider, model, pricing_snapshot)
            llm_models_used.add(f"{provider}:{model}")
            if llm_pricing_note is None:
                llm_pricing_note = pricing_note(provider, model, rates, pricing_version)

        if rates:
            cost = (input_tokens * rates["input"] + output_tokens * rates["output"]) / 1_000_000
        else:
            cost = 0.0

        blocks.append({
            "block_id":      nid,
            "label":         label,
            "type":          btype,
            "mode":          mode,
            "integration":   integration,
            "provider":      provider,
            "model":         model,
            "input_tokens":  input_tokens,
            "output_tokens": output_tokens,
            "cost_usd":      round(cost, 6),
            "note":          note,
        })

        total_input_tokens  += input_tokens
        total_output_tokens += output_tokens

    # Sum from block-level costs so multi-model/provider workflows estimate correctly.
    per_run_cost = sum(float(b.get("cost_usd", 0.0) or 0.0) for b in blocks)
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
        "model":                sorted(llm_models_used)[0] if llm_models_used else None,
        "models_used":          sorted(llm_models_used),
        "pricing_version":      pricing_snapshot.get("version"),
        "pricing_note":         llm_pricing_note or "No LLM-cost blocks in this workflow",
        "based_on_actuals":     has_actuals,
    }


@router.post("/{workflow_id}/compile", response_model=WorkflowDetailOut)
def compile_workflow_now(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """Explicitly trigger compilation for the current version."""
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
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
    _stamp(workflow)
    return workflow
