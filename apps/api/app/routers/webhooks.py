"""
Webhook endpoints for external services.

POST /webhooks/slack/interactions  — Slack approval button clicks
POST /webhooks/vercel              — Vercel deployment events (deployment.succeeded etc.)
POST /webhooks/github              — GitHub issue/PR events (issues.labeled, etc.)
POST /webhooks/inbound/{id}        — Generic inbound webhook trigger
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
        return False  # Reject: no secret configured — set SLACK_SIGNING_SECRET
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



# ── Inbound webhook trigger ───────────────────────────────────────────────────

@router.post("/inbound/{workflow_id}")
async def inbound_webhook(
    workflow_id: str,
    request: Request,
    db: Session = Depends(get_db),
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

    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    version = workflow.current_version
    nodes = version.graph.get("nodes", [])
    trigger_node = next(
        (n for n in nodes
         if n.get("data", {}).get("type") == "trigger"
         and n.get("data", {}).get("config", {}).get("event_type") == "webhook"),
        None,
    )
    if not trigger_node:
        raise HTTPException(status_code=400, detail="Workflow has no webhook trigger")

    webhook_secret = trigger_node.get("data", {}).get("config", {}).get("webhook_secret", "")
    if webhook_secret:
        sig_header = request.headers.get("X-Webhook-Signature", "")
        expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
        if not sig_header or not hmac.compare_digest(expected, sig_header):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    run = Run(
        workflow_version_id=version.id,
        triggered_by="webhook:inbound",
        status="pending",
        state={"_trigger": payload, "__triggered_by": "webhook:inbound"},
    )
    db.add(run)
    db.flush()
    db.commit()
    _redis().rpush(QUEUE_KEY, str(run.id))
    log.info("Inbound webhook triggered run %s for workflow %s", run.id, workflow_id)
    return {"ok": True, "run_id": str(run.id)}


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

    if not workspace_id:
        log.warning("Vercel webhook received with no workspace_id — ignoring to prevent cross-tenant fanout")
        return {"ok": False, "reason": "workspace_id query param required; re-register the webhook URL with ?workspace_id=<your-workspace-id>"}

    queued = _trigger_webhook_workflows(db, event_type, initial_state, workspace_id=workspace_id)
    return {"ok": True, "queued": len(queued), "run_ids": queued}


# ── GitHub webhook ────────────────────────────────────────────────────────────

def _verify_github_signature(body: bytes, signature: str) -> bool:
    secret = settings.github_webhook_secret
    if not secret:
        return False  # Reject: no secret configured — set GITHUB_WEBHOOK_SECRET
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


def _normalize_github_issue_labeled_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Normalize GitHub issue labeled webhook payload into a stable internal shape.
    Raises HTTPException(422) when required fields are missing.
    """
    issue = payload.get("issue") or {}
    repo = payload.get("repository") or {}
    label = (payload.get("label") or {}).get("name")

    issue_number = issue.get("number")
    repo_full_name = repo.get("full_name")

    if not issue_number or not repo_full_name or not label:
        raise HTTPException(status_code=422, detail="Missing required issue/repository/label fields")

    return {
        "event_type": "github_issue_labeled",
        "action": payload.get("action"),
        "delivery_id": payload.get("delivery_id"),
        "installation_id": (payload.get("installation") or {}).get("id"),
        "label": label,
        "repo": {
            "id": repo.get("id"),
            "full_name": repo_full_name,
            "name": repo.get("name"),
            "owner": (repo.get("owner") or {}).get("login"),
            "default_branch": repo.get("default_branch", "main"),
            "clone_url": repo.get("clone_url"),
        },
        "issue": {
            "id": issue.get("id"),
            "number": issue_number,
            "title": issue.get("title"),
            "body": issue.get("body") or "",
            "url": issue.get("html_url"),
            "author": (issue.get("user") or {}).get("login"),
            "labels": [l.get("name") for l in issue.get("labels", []) if l.get("name")],
        },
        "sender": {
            "login": (payload.get("sender") or {}).get("login"),
        },
    }


def _parse_repo_allowlist(raw: Any) -> set[str]:
    """Accept either list[str] or comma-separated string from trigger config."""
    if isinstance(raw, list):
        return {str(v).strip() for v in raw if str(v).strip()}
    if isinstance(raw, str):
        return {v.strip() for v in raw.split(",") if v.strip()}
    return set()


def _parse_string_list(raw: Any) -> list[str]:
    """Accept list[str] or comma-separated string as normalized list[str]."""
    if isinstance(raw, list):
        return [str(v).strip() for v in raw if str(v).strip()]
    if isinstance(raw, str):
        return [v.strip() for v in raw.split(",") if v.strip()]
    return []


def _labels_match(config: dict[str, Any], incoming_label: str, issue_labels: list[str], strict: bool) -> bool:
    mode = str(config.get("label_mode") or "").strip()
    configured_labels = _parse_string_list(config.get("labels"))

    if configured_labels:
        effective_mode = mode if mode in ("one_of", "all_of") else "one_of"
        if effective_mode == "one_of":
            return incoming_label in configured_labels or any(lbl in configured_labels for lbl in issue_labels)
        # all_of: only fire when the triggering label is one we care about
        if effective_mode == "all_of":
            if incoming_label not in configured_labels:
                return False
            issue_set = set(issue_labels)
            return all(lbl in issue_set for lbl in configured_labels)

    # Legacy / fallback — handles label: singular and label_mode: one_of with no labels list
    required = str(config.get("label") or "").strip()
    if not required:
        return not strict
    return incoming_label == required


def _repo_matches(config: dict[str, Any], incoming_repo: str, strict: bool) -> bool:
    repo_scope = str(config.get("repo_scope") or "allowlist").strip()

    if repo_scope == "allow_all":
        return True

    if repo_scope == "denylist":
        denylist = _parse_repo_allowlist(config.get("repo_denylist"))
        if not denylist:
            return not strict
        return incoming_repo not in denylist

    # default: allowlist
    allowlist = _parse_repo_allowlist(config.get("repo_allowlist") or config.get("repos"))
    if not allowlist:
        return not strict
    return incoming_repo in allowlist


def _trigger_github_workflows(
        db: Session, event_type: str, normalized: dict[str, Any], initial_state: dict[str, Any],
    workspace_id: str | None = None,
) -> list[str]:
    """
        Find workflow versions with a trigger block matching workflow-defined contract:
            - event_type in {"github_issue", "github_issue_labeled"}
            - config.label must equal incoming label
            - optional config.repo_allowlist must include incoming repo full_name

    If workspace_id is provided, only triggers workflows in that workspace.
    """
    query = db.query(WorkflowVersion).join(
        Workflow, Workflow.current_version_id == WorkflowVersion.id
    )
    if workspace_id:
        query = query.filter(Workflow.workspace_id == workspace_id)
    versions = query.all()

    queued: list[str] = []
    incoming_label = normalized["label"]
    incoming_repo = normalized["repo"]["full_name"]
    issue_labels = normalized["issue"]["labels"]

    for version in versions:
        nodes = version.graph.get("nodes", [])
        matched_trigger = None

        for node in nodes:
            data = node.get("data", {})
            if data.get("type") != "trigger":
                continue

            config = data.get("config", {})
            trigger_event = config.get("event_type")
            if trigger_event not in (event_type, "github_issue_labeled"):
                continue

            enforcement = str(config.get("enforcement") or "strict").strip()
            strict = enforcement != "permissive"

            if not _labels_match(config, incoming_label, issue_labels, strict):
                continue

            if not _repo_matches(config, incoming_repo, strict):
                continue

            matched_trigger = node
            break

        if not matched_trigger:
            continue

        run = Run(
            workflow_version_id=version.id,
            triggered_by=f"github:{event_type}:{incoming_label}",
            status="pending",
            state={**initial_state, "__triggered_by": f"github:{event_type}"},
        )
        db.add(run)
        db.flush()
        db.commit()
        _redis().rpush(QUEUE_KEY, str(run.id))
        queued.append(str(run.id))
        log.info("GitHub %s (label=%s repo=%s) triggered run %s for version %s", event_type, incoming_label, incoming_repo, run.id, version.id)

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

    normalized = _normalize_github_issue_labeled_payload(payload)

    initial_state = {
        "github_issue": {
            "issue_number": normalized["issue"]["number"],
            "title": normalized["issue"]["title"],
            "body": normalized["issue"]["body"],
            "url": normalized["issue"]["url"],
            "author": normalized["issue"]["author"],
            "labels": normalized["issue"]["labels"],
            "label_added": normalized["label"],
            "repo_full_name": normalized["repo"]["full_name"],
            "repo_name": normalized["repo"]["name"],
            "repo_owner": normalized["repo"]["owner"],
            "default_branch": normalized["repo"]["default_branch"],
            "clone_url": normalized["repo"]["clone_url"],
        },
        "github_trigger": normalized,
    }

    queued = _trigger_github_workflows(db, "github_issue", normalized, initial_state, workspace_id)
    return {
        "ok": True,
        "queued": len(queued),
        "run_ids": queued,
        "label": normalized["label"],
        "repo": normalized["repo"]["full_name"],
    }



