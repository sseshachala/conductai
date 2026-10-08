"""Generic inbound + Vercel deploy webhooks (split from webhooks.py).

Second link of the route-registration chain (see webhooks_slack).
"""
import hashlib
import hmac
import json
import structlog
from typing import Any
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract
from app.routers.webhooks_common import (
    _enqueue_run,
    _redis,
)
from app.routers.webhooks_slack import router

log = structlog.get_logger("app.routers.webhooks")


# ── Inbound webhook trigger ───────────────────────────────────────────────────

@router.post("/inbound/{project_slug}/{workflow_id}")
@router.post("/inbound/{workflow_id}")
async def inbound_webhook(
    workflow_id: str,
    request: Request,
    db: Session = Depends(get_db),
    project_slug: str | None = None,
):
    """
    Receive an inbound POST and fire a workflow run whose trigger is configured
    as event_type=\"webhook\".  Optionally verifies an HMAC-SHA256 signature
    when the trigger node has a webhook_secret set.
    """
    body = await request.body()
    try:
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {"raw": body.decode(errors="replace")}

    # Webhook auth is via HMAC signature, not workspace cookie — query by ID only.
    # Use SET LOCAL row_security = off so RLS on workflows does not block this lookup.
    db.execute(__import__("sqlalchemy").text("SET LOCAL row_security = off"))
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Re-enable RLS and set workspace context from the workflow for subsequent queries.
    db.execute(__import__("sqlalchemy").text("SET LOCAL row_security = on"))
    from app.core.workspace_context import set_workspace_rls
    set_workspace_rls(db, str(workflow.workspace_id))

    version = workflow.current_version
    nodes = version.graph.get("nodes", [])
    trigger_node = next(
        (n for n in nodes if n.get("data", {}).get("type") == "trigger"),
        None,
    )
    if not trigger_node:
        raise HTTPException(status_code=400, detail="Workflow has no trigger node")

    trigger_config = trigger_node.get("data", {}).get("config", {})
    raw_secret = trigger_config.get("webhook_secret", "")
    git_provider = trigger_config.get("git_provider", "github")

    # Fail-closed: require a webhook secret on every inbound trigger.
    if not raw_secret:
        raise HTTPException(status_code=401, detail="Workflow has no webhook secret configured")

    from app.core.crypto import decrypt as _decrypt
    import base64 as _base64
    try:
        webhook_secret = _decrypt(raw_secret)["secret"]
    except Exception:
        # Fallback for old installs that stored a plaintext secret before encryption
        # was introduced.  A real ciphertext blob is base64-encoded and will be
        # significantly longer than a typical webhook secret (>40 chars after
        # base64-decode attempts).  If the raw value looks like a short human-readable
        # secret (<=128 chars, no null bytes) treat it as plaintext.  Otherwise
        # fail closed — using a garbled ciphertext as the expected HMAC key would
        # accept any attacker-crafted signature computed against that same ciphertext.
        is_likely_ciphertext = False
        try:
            decoded = _base64.b64decode(raw_secret, validate=True)
            # A 12-byte nonce + AES-GCM ciphertext will always be >40 bytes
            is_likely_ciphertext = len(decoded) > 40
        except Exception:
            pass
        if is_likely_ciphertext:
            log.error(
                "webhook.inbound_secret_decrypt_failed",
                workflow_id=workflow_id,
                note="Stored secret looks like a corrupted ciphertext. "
                     "Re-save the webhook secret in the workflow trigger config.",
            )
            raise HTTPException(
                status_code=500,
                detail="Webhook secret is corrupted — re-save it in the workflow trigger settings.",
            )
        # Short plaintext secret from an old install — accept as-is.
        webhook_secret = raw_secret

    if git_provider == "gitlab":
        # GitLab sends the secret as a static token header
        incoming = request.headers.get("X-Gitlab-Token", "")
        if not incoming or not hmac.compare_digest(webhook_secret, incoming):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        # GitHub and Bitbucket both use HMAC-SHA256 (X-Hub-Signature-256)
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
        if not sig_header or not hmac.compare_digest(expected, sig_header):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Estimate turn budget from the trigger payload so webhook runs are guarded
    # the same way manual runs are when the preflight banner is accepted.
    from app.routers.workflows import _estimate_turns_for_graph
    issue_title = (
        payload.get("issue", {}).get("title")
        or payload.get("pull_request", {}).get("title")
        or ""
    )
    issue_body = (
        payload.get("issue", {}).get("body")
        or payload.get("pull_request", {}).get("body")
        or ""
    )
    try:
        graph = version.graph or {}
        pf = _estimate_turns_for_graph(graph, issue_title, issue_body, workspace_id=str(workflow.workspace_id), db=db)
        suggested_turns = pf["suggested_max_turns"]
    except Exception:
        suggested_turns = 20

    initial_state = {
        "_trigger": payload,
        "__triggered_by": "webhook:inbound",
    }
    initial_state = enrich_run_state_contract(
        initial_state,
        source="webhook:inbound",
        trigger_provider=git_provider,
        workflow_id=str(workflow_id),
        workspace_id=str(workflow.workspace_id),
        max_turns=suggested_turns,
    )
    try:
        initial_state = validate_run_start_inputs(initial_state)
    except InputContractError as err:
        raise HTTPException(status_code=422, detail=str(err))

    run = Run(
        workflow_version_id=version.id,
        workspace_id=workflow.workspace_id,
        triggered_by="webhook:inbound",
        status="pending",
        state=initial_state,
        max_turns=suggested_turns,
    )
    db.add(run)
    db.commit()
    try:
        _enqueue_run(str(run.id))
    except Exception as _enqueue_err:
        log.error("webhook.inbound_enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))
        raise HTTPException(status_code=503, detail="Webhook received but queue is unavailable")
    log.info("webhook.inbound_triggered", run_id=str(run.id), workflow_id=workflow_id, max_turns=suggested_turns)
    return {"ok": True}


# ── Deploy webhook helpers ────────────────────────────────────────────────────

def _trigger_webhook_workflows(
    db: Session,
    event_type: str,
    initial_state: dict[str, Any],
    workspace_id: str | None = None,
) -> list[str]:
    """
    Find workflows whose trigger block config.event_type matches `event_type`
    OR is the generic value "webhook" (matches all webhook events).
    workspace_id MUST be provided to scope to a single tenant; omitting it is
    only safe for internal callers that already scope the query themselves.
    Returns list of queued run IDs.
    """
    from app.models.workflow import Workflow, WorkflowVersion
    import uuid as uuid_mod

    q = db.query(WorkflowVersion).join(
        Workflow, Workflow.current_version_id == WorkflowVersion.id
    )
    if workspace_id:
        q = q.filter(Workflow.workspace_id == workspace_id)
    versions = q.all()

    # Build all matching Run objects first, flush to assign IDs, then commit once.
    # This keeps the DB write atomic across all triggered workflows, and separates
    # the Redis enqueue step from the commit step so a Redis failure doesn't leave
    # partial DB state (all runs committed) or orphan any run (all enqueued after commit).
    matching_runs: list[Run] = []
    for version in versions:
        nodes = version.graph.get("nodes", [])
        has_webhook_trigger = any(
            n.get("data", {}).get("type") == "trigger" and
            n.get("data", {}).get("config", {}).get("event_type") in ("webhook", event_type)
            for n in nodes
        )
        if not has_webhook_trigger:
            continue

        run = Run(
            workflow_version_id=version.id,
            workspace_id=uuid_mod.UUID(workspace_id) if workspace_id else None,
            triggered_by=f"webhook:{event_type}",
            status="pending",
            state={**initial_state, "__triggered_by": f"webhook:{event_type}"},
        )
        db.add(run)
        matching_runs.append(run)

    if not matching_runs:
        return []

    # Single flush + commit for all runs — all-or-nothing.
    db.flush()
    db.commit()

    queued: list[str] = []
    r = _redis()
    for run in matching_runs:
        try:
            _enqueue_run(str(run.id))
            queued.append(str(run.id))
            log.info("webhook.triggered", event_type=event_type, run_id=str(run.id),
                     version_id=str(run.workflow_version_id))
        except Exception as _enqueue_err:
            log.error("webhook.enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))
            # Run is committed as 'pending' — log prominently so ops can recover.

    return queued


@router.post("/vercel")
async def vercel_webhook(
    request: Request,
    db: Session = Depends(get_db),
    workspace_id: str | None = None,
):
    """
    Receive Vercel deployment webhooks.
    Configure in Vercel → Project → Settings → Webhooks.
    Register the URL as: <api_base_url>/webhooks/vercel?workspace_id=<workspace_id>
    so events are scoped to the registering workspace only.
    Events: deployment.succeeded, deployment.failed, deployment.ready, etc.
    """
    body = await request.body()

    # Fail-closed signature verification — reject if secret not configured
    vercel_secret = settings.vercel_webhook_secret if hasattr(settings, "vercel_webhook_secret") else ""
    if not vercel_secret:
        raise HTTPException(status_code=401, detail="Vercel webhook secret not configured")
    sig = request.headers.get("x-vercel-signature", "")
    expected = hmac.new(vercel_secret.encode(), body, hashlib.sha1).hexdigest()  # type: ignore[attr-defined]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=401, detail="Invalid Vercel signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type", "deployment.unknown")
    deployment = payload.get("payload", {}).get("deployment", {})
    project = payload.get("payload", {}).get("project", {})

    initial_state = {
        "vercel_webhook": {
            "event": event_type,
            "deployment_id": deployment.get("id"),
            "url": f"https://{deployment.get('url')}" if deployment.get("url") else None,
            "state": deployment.get("readyState") or deployment.get("state"),
            "project_name": project.get("name"),
            "branch": deployment.get("meta", {}).get("githubCommitRef"),
            "commit_sha": deployment.get("meta", {}).get("githubCommitSha"),
            "commit_message": deployment.get("meta", {}).get("githubCommitMessage"),
        }
    }

    # Only trigger workflows on meaningful terminal states
    trigger_on = {"deployment.succeeded", "deployment.ready", "deployment.failed", "deployment.error"}
    if event_type not in trigger_on:
        return {"ok": True, "queued": 0, "reason": f"event {event_type} not a trigger"}

    if not workspace_id:
        log.warning("webhook.vercel_no_workspace")
        return {"ok": False, "reason": "workspace_id query param required; re-register the webhook URL with ?workspace_id=<your-workspace-id>"}

    queued = _trigger_webhook_workflows(db, event_type, initial_state, workspace_id=workspace_id)
    return {"ok": True, "queued": len(queued), "run_ids": queued}
