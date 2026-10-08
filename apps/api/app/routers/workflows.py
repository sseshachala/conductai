"""Workflow trigger + repo-sync endpoints, and the public ``app.routers.workflows`` facade.

The ``/workflows`` router is shared across workflows_crud, workflows_validation,
workflows_yaml and this module (last link of the registration chain — see
workflows_crud). ``main.py`` includes ``workflows.router``; helpers that other
modules import from here are re-exported below.
"""
import structlog
from uuid import UUID
from fastapi import Body, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_permission
from app.core.database import get_db

log = structlog.get_logger(__name__)

from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion
from app.runtime.input_contract import InputContractError, validate_run_start_inputs, validate_required_inputs
from app.runtime.run_contract import enrich_run_state_contract


# Playbook catalog data lives in playbooks.py — import here so workflow CRUD
# functions (_stamp, create_workflow, register_workflow_webhook, test_trigger)
# can reference registry constants without duplicating them.
from app.routers.playbooks import (  # noqa: E402
    _TEMPLATE_PLAYBOOKS,
)
from app.routers.workflows_preflight import _estimate_turns_for_graph
from app.routers.workflows_crud import _run_compiler
from app.routers.workflows_yaml import router

# Re-exports for callers that import these helpers from app.routers.workflows.
from app.routers.workflows_git_hooks import _deregister_git_webhook  # noqa: E402,F401
from app.routers.workflows_preflight import _resolve_preflight_key  # noqa: E402,F401


@router.post("/{workflow_id}/trigger")
def test_trigger(
    workflow_id: UUID,
    request: Request = None,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
    caller_id: str = Depends(get_user_id),
):
    """
    Authenticated test trigger. When payload is empty, uses the playbook's
    built-in test_trigger.payload (defined in the YAML). Bypasses webhook
    HMAC — callers authenticate via Clerk JWT instead.
    """
    import pathlib, yaml as _yaml
    from app.modules.auth.federation.workflow import prepare_run, attach_run
    federation = prepare_run(request, workspace_id)
    import redis as _redis_mod
    from app.core.config import settings as _settings

    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)

    # Guard policy check — enforced regardless of caller (MCP, CLI, canvas, HTTP)
    try:
        import uuid as _uuid
        from app.modules.guard.policy_engine import compute_policy
        from app.guard.policy import _is_proxy_rule
        _rules = compute_policy(db, _uuid.UUID(workspace_id), "proxy")
        _input_text = str(workflow_id)
        for _r in _rules:
            if _is_proxy_rule(_r):
                continue  # proxy-only rules don't apply to tool dispatch
            import re as _re
            _pat = _r.get("match_pattern")
            if _pat and not _re.search(_pat, _input_text, _re.IGNORECASE):
                continue
            _mt = (_r.get("match_tool") or "*").lower()
            if _mt not in ("*", "workflow"):
                continue
            if (_r.get("action") or "audit").lower() == "block":
                raise HTTPException(status_code=403, detail=f"[ConductGuard] {_r.get('message') or _r.get('rule_id')}")
    except HTTPException:
        raise
    except Exception as _guard_err:
        # ponytail: fail-open on engine error so a Guard outage can't wedge every run,
        # but log the bypass so operators can see when enforcement was silently skipped.
        log.warning(
            "guard.engine_error.fail_open",
            workflow_id=str(workflow_id),
            workspace_id=str(workspace_id),
            surface="proxy",
            error=str(_guard_err),
        )
        from app.modules.guard.observability import record_fail_open
        record_fail_open(db, workspace_id=workspace_id, surface="proxy", error=_guard_err)

    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Extract CLI-only keys before merging with the YAML test payload.
    # inputs: dict of {{inputs.x}} values supplied via `conduct run --input key=val`.
    # __manual: True signals a manual/schedule trigger — bypasses trigger-shape validation.
    run_inputs: dict = payload.pop("inputs", {})
    is_manual_flag: bool = bool(payload.pop("__manual", False))
    # #1515 P1 — canvas Run → Lens session convergence.
    # lens_attach=True auto-mints a bare Lens session (or reuses lens_session_id)
    # so the run appears as a RunBubble in that session. Silent no-op for CLI/webhook.
    lens_attach: bool = bool(payload.pop("lens_attach", False))
    lens_session_id_raw = payload.pop("lens_session_id", None)

    # Always load the playbook's built-in test_trigger.payload, then merge any
    # caller-supplied overrides on top. This lets --repo override the repo fields
    # without wiping advisory/issue data baked into the test_trigger.
    base_payload: dict = {}
    if workflow.playbook_slug and workflow.playbook_slug in _TEMPLATE_PLAYBOOKS:
        playbook_file = _TEMPLATE_PLAYBOOKS[workflow.playbook_slug]
        playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / playbook_file
        if playbook_path.exists():
            raw = _yaml.safe_load(playbook_path.read_text()) or {}
            base_payload = raw.get("test_trigger", {}).get("payload", {})
    payload = {**base_payload, **payload}  # caller overrides win

    # Override the repo fields in the payload with the CONFIGURED repo for this workflow.
    # The YAML test_trigger.payload has a hardcoded example repo — we always replace it
    # with the actual installed repo so the test run targets the right repo.
    configured_repo: str | None = None
    if workflow.current_version:
        nodes = (workflow.current_version.graph or {}).get("nodes", [])
        trigger_node = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
        if trigger_node:
            cfg = trigger_node.get("data", {}).get("config", {})
            allowlist_raw = cfg.get("repo_allowlist") or ""
            first_repo = next(iter(r.strip() for r in allowlist_raw.split(",") if r.strip()), None)
            configured_repo = first_repo
    configured_repo = configured_repo or workflow.github_hook_repo
    if configured_repo and "/" in configured_repo and not payload.get("repository", {}).get("_caller_set"):
        owner, repo_name = configured_repo.split("/", 1)
        payload.setdefault("repository", {})
        payload["repository"] = {
            **payload.get("repository", {}),
            "full_name": configured_repo,
            "name": repo_name,
            "owner": {"login": owner},
            "clone_url": f"https://github.com/{configured_repo}.git",
        }

    if not payload:
        raise HTTPException(status_code=400, detail="No payload provided and no test_trigger defined for this playbook")

    version = workflow.current_version
    try:
        graph = version.graph or {}
        # min_turns: honour YAML-declared floor and workflow DB override
        yaml_min = 0
        if version.yaml_source:
            try:
                raw_yaml = _yaml.safe_load(version.yaml_source) or {}
                yaml_min = int((raw_yaml.get("inputs", {}).get("min_turns", {}) or {}).get("default", 0))
            except Exception:
                pass
        min_turns = max(yaml_min, workflow.default_max_turns or 0)
        pf = _estimate_turns_for_graph(graph, payload.get("title", ""), payload.get("body", ""), min_turns, workspace_id, db, workflow_id=str(workflow.id))
        suggested_turns = pf["suggested_max_turns"]
    except Exception:
        suggested_turns = max(20, workflow.default_max_turns or 0)

    # Caller-supplied max_turns override (from Test Run dialog) takes final precedence
    if caller_max_turns := payload.get("__max_turns_override"):
        suggested_turns = max(suggested_turns, int(caller_max_turns))

    # Normalize GitHub issue payloads to match the real webhook path so that
    # {{_trigger.issue_number}}, {{_trigger.repo_full_name}}, etc. resolve in
    # the same way whether this is a real webhook or a test trigger.
    _issue = payload.get("issue") or {}
    _repo = payload.get("repository") or {}
    _label = (payload.get("label") or {}).get("name", "")
    _caller_email: str | None = None
    if caller_id and not caller_id.startswith("api-key:"):
        try:
            from app.models.user import User as _User
            _u = db.query(_User).filter(_User.clerk_id == caller_id).first()
            if _u:
                _caller_email = _u.email
        except Exception:
            pass
    _initial_state: dict = {"__triggered_by": "manual:test_trigger", "__max_turns": suggested_turns, "__user_email": _caller_email}
    if _issue:
        _initial_state["github_issue"] = {
            "issue_number": _issue.get("number"),
            "title": _issue.get("title"),
            "body": _issue.get("body") or "",
            "url": _issue.get("html_url", ""),
            "author": (_issue.get("user") or {}).get("login", ""),
            "labels": [l.get("name", "") for l in (_issue.get("labels") or [])],
            "label_added": _label,
            "repo_full_name": _repo.get("full_name", ""),
            "repo_name": _repo.get("name", ""),
            "repo_owner": (_repo.get("owner") or {}).get("login", ""),
            "default_branch": _repo.get("default_branch", "main"),
            "clone_url": _repo.get("clone_url", ""),
        }
        _initial_state["github_trigger"] = payload
    elif is_manual_flag:
        # Manual/schedule trigger from CLI — no trigger envelope needed.
        _initial_state["__manual"] = True
    else:
        # Non-GitHub trigger — keep raw payload as _trigger
        _initial_state["_trigger"] = payload

    # Propagate CLI --input values into state["inputs"] so {{inputs.x}} refs resolve.
    if run_inputs:
        _initial_state["inputs"] = run_inputs

    _initial_state = enrich_run_state_contract(
        _initial_state,
        source="manual:test_trigger",
        trigger_provider="github" if _issue else "manual",
        workflow_id=str(workflow_id),
        workspace_id=workspace_id,
        max_turns=suggested_turns,
    )

    try:
        _initial_state = validate_run_start_inputs(_initial_state)
    except InputContractError as err:
        raise HTTPException(status_code=422, detail=str(err))

    # Generic per-playbook required inputs check (#734).
    # Reads workflow's inputs_spec, checks each input with required_at == "run".
    _inputs_spec = (workflow.current_version.graph or {}).get("inputs_spec") or {}
    _missing = validate_required_inputs(_inputs_spec, _initial_state.get("inputs"), phase="run")
    if _missing:
        labels = ", ".join(m["label"] for m in _missing)
        raise HTTPException(
            status_code=422,
            detail={
                "error": "missing_required_inputs",
                "message": f"Required inputs missing: {labels}",
                "missing": _missing,
            },
        )

    # #1515 P1 — resolve the Lens session (existing or fresh) before insert
    # so Run.session_id is set at creation. Publisher no-ops on NULL, so this
    # is the seam that makes RunBubble receive SSE events.
    lens_session_id: _uuid.UUID | None = None
    if lens_attach or lens_session_id_raw:
        from app.modules.glens.models import GlensChatSession
        if lens_session_id_raw:
            try:
                lens_session_id = _uuid.UUID(str(lens_session_id_raw))
            except ValueError:
                raise HTTPException(status_code=422, detail="lens_session_id must be a UUID")
            sess = db.query(GlensChatSession).filter(
                GlensChatSession.id == lens_session_id,
                GlensChatSession.workspace_id == _uuid.UUID(workspace_id),
            ).first()
            if not sess:
                raise HTTPException(status_code=404, detail="lens_session_id not found in workspace")
        else:
            sess = GlensChatSession(
                workspace_id=_uuid.UUID(workspace_id),
                title=f"Run: {workflow.name}"[:120],
                messages="[]",
            )
            db.add(sess)
            db.flush()
            lens_session_id = sess.id

    run = Run(
        workflow_version_id=version.id,
        workspace_id=workflow.workspace_id,
        triggered_by="manual:test_trigger",
        status="pending",
        state=_initial_state,
        max_turns=suggested_turns,
        session_id=lens_session_id,
    )
    db.add(run)
    attach_run(db, run, federation)
    db.commit()

    # #1515 P1 — append run_started envelope so RunBubble rehydrates on
    # session load (matches the actor helpers.py path). Fail-open: envelope
    # failure must not fail the run creation.
    if lens_session_id is not None:
        try:
            import json as _json_env
            from app.modules.glens.models import GlensChatSession as _GCS
            _sess = db.query(_GCS).filter(_GCS.id == lens_session_id).first()
            if _sess is not None:
                _messages = _json_env.loads(_sess.messages or "[]")
                _messages.append({
                    "role": "assistant",
                    "content": _json_env.dumps({
                        "run_started": {
                            "run_id": str(run.id),
                            "workflow_name": workflow.name,
                            "status": run.status,
                        }
                    }),
                })
                _sess.messages = _json_env.dumps(_messages)
                db.commit()
        except Exception as _env_err:
            db.rollback()
            log.warning(
                "workflow.test_triggered.envelope_failed",
                run_id=str(run.id), session_id=str(lens_session_id), error=str(_env_err),
            )

    try:
        r = _redis_mod.from_url(_settings.redis_url, decode_responses=True)
        r.rpush("marshal:runs:queue", str(run.id))
    except Exception as _enqueue_err:
        import logging as _logging
        _logging.getLogger(__name__).error(
            "workflow.test_triggered.enqueue_failed run_id=%s err=%s", run.id, _enqueue_err
        )
        raise HTTPException(status_code=503, detail="Run created but queue is unavailable")

    log.info("workflow.test_triggered", workflow_id=str(workflow_id), run_id=str(run.id), playbook_slug=workflow.playbook_slug)
    return {
        "ok": True,
        "run_id": str(run.id),
        "max_turns": suggested_turns,
        "session_id": str(lens_session_id) if lens_session_id else None,
    }


class SyncRequest(BaseModel):
    ref: str | None = None  # branch / tag / sha; default = repo default branch


@router.post("/{workflow_id}/sync")
def sync_workflow(
    workflow_id: UUID,
    body: SyncRequest = Body(default=SyncRequest()),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    """
    Fetch the YAML at ``workflow.source_repo:source_path`` from GitHub,
    validate it, and create a new WorkflowVersion if the content changed.
    No-op when the source matches the current version.
    """
    from app.dsl.sync import SyncError, sync_workflow_from_repo

    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id, Workflow.archived_at.is_(None)).first()
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
