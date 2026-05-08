"""
Webhook endpoints for external services.

POST /webhooks/slack/interactions  — Slack approval button clicks
POST /webhooks/vercel              — Vercel deployment events (deployment.succeeded etc.)
POST /webhooks/railway             — Railway deployment events
POST /webhooks/github              — GitHub issue/PR events (issues.labeled, etc.)
"""
import hashlib
import hmac
import json
import logging
import time
from typing import Any
from urllib.parse import unquote_plus

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion

log = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

QUEUE_KEY = "marshal:runs:queue"


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify Slack's request signing (v0 scheme)."""
    if not settings.slack_signing_secret:
        return True  # Skip verification in dev if secret not configured
    if abs(time.time() - int(timestamp)) > 300:
        return False  # Replay attack guard: reject if older than 5 minutes
    base = f"v0:{timestamp}:{request_body.decode()}"
    expected = "v0=" + hmac.new(
        settings.slack_signing_secret.encode(),
        base.encode(),
        hashlib.sha256,
    ).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


@router.post("/slack/interactions")
async def slack_interactions(request: Request, db: Session = Depends(get_db)):
    """
    Handle Slack interactive component payloads.
    Slack sends a URL-encoded body with a 'payload' field containing JSON.
    """
    body = await request.body()

    # Verify signature if signing secret is configured
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")
    if not _verify_slack_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Slack sends application/x-www-form-urlencoded with a 'payload' key
    body_str = body.decode()
    if body_str.startswith("payload="):
        payload_str = unquote_plus(body_str[len("payload="):])
    else:
        payload_str = body_str

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid payload JSON")

    # Extract action
    actions = payload.get("actions", [])
    if not actions:
        return {"ok": True}

    action = actions[0]
    action_id = action.get("action_id", "")
    value = action.get("value", "")

    if action_id not in ("approve_run", "reject_run"):
        return {"ok": True}

    # Value format: "approve:{run_id}" or "reject:{run_id}"
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Invalid action value format")

    decision_word, run_id_str = parts
    decision = "approved" if decision_word == "approve" else "rejected"

    run = db.query(Run).filter(Run.id == run_id_str).first()
    if not run:
        log.warning("Slack interaction for unknown run %s", run_id_str)
        return {"ok": True}

    if run.status != "paused":
        log.info("Run %s already %s — ignoring duplicate approval", run_id_str, run.status)
        return {"ok": True}

    block_id = run.current_block_id or ""
    approver = payload.get("user", {}).get("name", "slack-user")

    state = dict(run.state or {})
    state[f"__approval_{block_id}"] = decision
    state[f"__approver_{block_id}"] = approver
    run.state = state
    run.status = "pending"
    run.paused_at = None
    db.commit()

    event = RunEvent(
        run_id=run_id_str,
        block_id=block_id,
        kind="approval_received",
        payload={"decision": decision, "approver": approver, "source": "slack"},
    )
    db.add(event)
    db.commit()

    _redis().rpush(QUEUE_KEY, run_id_str)
    log.info("Run %s approval: %s by %s — re-queued", run_id_str, decision, approver)

    return {"ok": True}


# ── Deploy webhook helpers ────────────────────────────────────────────────────

def _trigger_webhook_workflows(db: Session, event_type: str, initial_state: dict[str, Any]) -> list[str]:
    """
    Find all workflows whose trigger block config.event_type matches `event_type`
    OR is the generic value "webhook" (matches all webhook events).
    Returns list of queued run IDs.
    """
    from app.models.workflow import Workflow, WorkflowVersion
    import uuid as uuid_mod

    versions = db.query(WorkflowVersion).join(
        Workflow, Workflow.current_version_id == WorkflowVersion.id
    ).all()

    queued: list[str] = []
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
            triggered_by=f"webhook:{event_type}",
            status="pending",
            state={**initial_state, "__triggered_by": f"webhook:{event_type}"},
        )
        db.add(run)
        db.flush()
        db.commit()
        _redis().rpush(QUEUE_KEY, str(run.id))
        queued.append(str(run.id))
        log.info("Webhook %s triggered run %s for version %s", event_type, run.id, version.id)

    return queued


@router.post("/vercel")
async def vercel_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Vercel deployment webhooks.
    Configure in Vercel → Project → Settings → Webhooks.
    Events: deployment.succeeded, deployment.failed, deployment.ready, etc.
    """
    body = await request.body()

    # Optional signature verification
    vercel_secret = settings.vercel_webhook_secret if hasattr(settings, "vercel_webhook_secret") else ""
    if vercel_secret:
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

    queued = _trigger_webhook_workflows(db, event_type, initial_state)
    return {"ok": True, "queued": len(queued), "run_ids": queued}


@router.post("/railway")
async def railway_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Receive Railway deployment webhooks.
    Configure in Railway → Project → Settings → Webhooks.
    Events: DEPLOY_SUCCESS, DEPLOY_FAILED, etc.
    """
    body = await request.body()

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type", "UNKNOWN")
    deployment = payload.get("deployment", {})
    service = payload.get("service", {})
    project = payload.get("project", {})

    initial_state = {
        "railway_webhook": {
            "event": event_type,
            "deployment_id": deployment.get("id"),
            "status": deployment.get("status"),
            "url": deployment.get("url"),
            "service_name": service.get("name"),
            "service_id": service.get("id"),
            "project_name": project.get("name"),
            "environment": payload.get("environment", {}).get("name"),
        }
    }

    trigger_on = {"DEPLOY_SUCCESS", "DEPLOY_FAILED", "DEPLOY_CRASHED"}
    if event_type not in trigger_on:
        return {"ok": True, "queued": 0, "reason": f"event {event_type} not a trigger"}

    queued = _trigger_webhook_workflows(db, event_type, initial_state)
    return {"ok": True, "queued": len(queued), "run_ids": queued}


# ── GitHub webhook ────────────────────────────────────────────────────────────

def _verify_github_signature(body: bytes, signature: str) -> bool:
    secret = settings.github_webhook_secret
    if not secret:
        return True  # Skip in dev if not configured
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


def _trigger_github_workflows(
    db: Session, event_type: str, label_filter: str, initial_state: dict[str, Any],
    workspace_id: str | None = None,
) -> list[str]:
    """
    Find workflow versions with a trigger block matching:
      - event_type == "github_issue"
      - config.label == label_filter (or label_filter is empty = match all)
    If workspace_id is provided, only triggers workflows in that workspace.
    """
    import uuid as uuid_mod

    query = db.query(WorkflowVersion).join(
        Workflow, Workflow.current_version_id == WorkflowVersion.id
    )
    if workspace_id:
        query = query.filter(Workflow.workspace_id == workspace_id)
    versions = query.all()

    queued: list[str] = []
    for version in versions:
        nodes = version.graph.get("nodes", [])
        match = any(
            n.get("data", {}).get("type") == "trigger" and
            n.get("data", {}).get("config", {}).get("event_type") == event_type and
            (
                not n.get("data", {}).get("config", {}).get("label") or
                n.get("data", {}).get("config", {}).get("label") == label_filter
            )
            for n in nodes
        )
        if not match:
            continue

        run = Run(
            workflow_version_id=version.id,
            triggered_by=f"github:{event_type}:{label_filter}",
            status="pending",
            state={**initial_state, "__triggered_by": f"github:{event_type}"},
        )
        db.add(run)
        db.flush()
        db.commit()
        _redis().rpush(QUEUE_KEY, str(run.id))
        queued.append(str(run.id))
        log.info("GitHub %s (label=%s) triggered run %s for version %s", event_type, label_filter, run.id, version.id)

    return queued


@router.post("/github")
async def github_webhook(
    request: Request,
    db: Session = Depends(get_db),
    workspace_id: str | None = None,
):
    """
    Receive GitHub webhook events.
    Configure in GitHub → repo → Settings → Webhooks.
    Listens for: issues (labeled), push, pull_request (opened, merged).

    Pass ?workspace_id=<uuid> in the webhook URL to scope triggers to a single
    workspace (required in multi-tenant deployments).
    """
    body = await request.body()

    sig = request.headers.get("X-Hub-Signature-256", "")
    if not _verify_github_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid GitHub signature")

    event = request.headers.get("X-GitHub-Event", "unknown")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Only handle issue labeled events for now
    if event != "issues" or payload.get("action") != "labeled":
        return {"ok": True, "queued": 0, "reason": f"event {event}/{payload.get('action')} not handled"}

    issue = payload.get("issue", {})
    label = payload.get("label", {}).get("name", "")
    repo = payload.get("repository", {})

    initial_state = {
        "github_issue": {
            "issue_number": issue.get("number"),
            "title": issue.get("title"),
            "body": issue.get("body") or "",
            "url": issue.get("html_url"),
            "author": issue.get("user", {}).get("login"),
            "labels": [l["name"] for l in issue.get("labels", [])],
            "label_added": label,
            "repo_full_name": repo.get("full_name"),
            "repo_name": repo.get("name"),
            "repo_owner": repo.get("owner", {}).get("login"),
            "default_branch": repo.get("default_branch", "main"),
            "clone_url": repo.get("clone_url"),
        }
    }

    queued = _trigger_github_workflows(db, "github_issue", label, initial_state, workspace_id)
    return {"ok": True, "queued": len(queued), "run_ids": queued, "label": label}


# ── Deploy Delegator manual trigger ──────────────────────────────────────────

@router.post("/deploy-delegator")
async def deploy_delegator(request: Request, db: Session = Depends(get_db)):
    """
    Manually trigger the Deploy Delegator workflow (deploys delegator-backend
    and delegator-ui to Railway). Looks for workflows with trigger block
    event_type = 'deploy_delegator'.

    Optionally accepts a JSON body: {"ref": "main", "triggered_by": "user"}
    """
    try:
        body = await request.body()
        payload = json.loads(body) if body else {}
    except json.JSONDecodeError:
        payload = {}

    initial_state = {
        "deploy_trigger": {
            "ref": payload.get("ref", "main"),
            "triggered_by": payload.get("triggered_by", "manual"),
        }
    }

    queued = _trigger_webhook_workflows(db, "deploy_delegator", initial_state)
    return {"ok": True, "queued": len(queued), "run_ids": queued}

