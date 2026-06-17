"""
Webhook endpoints for external services.

POST /webhooks/slack/interactions  — Slack approval button clicks
POST /webhooks/vercel              — Vercel deployment events (deployment.succeeded etc.)
POST /webhooks/github              — GitHub issue/PR events (issues.labeled, etc.)
POST /webhooks/inbound/{id}  — Generic inbound webhook trigger\nPOST /webhooks/clerk          — Clerk user.created → create workspace + Guard
"""
import hashlib
import hmac
import json
import structlog
import time
from typing import Any
from urllib.parse import unquote_plus

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

QUEUE_KEY = "marshal:runs:queue"
QUEUE_MAX_DEPTH = 50_000


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _enqueue_run(run_id: str) -> None:
    r = _redis()
    depth = r.llen(QUEUE_KEY)
    if depth >= QUEUE_MAX_DEPTH:
        raise HTTPException(
            status_code=503,
            detail=f"Run queue is at capacity ({depth} pending). Try again shortly.",
        )
    r.rpush(QUEUE_KEY, run_id)


def _verify_slack_signature(request_body: bytes, timestamp: str, signature: str, signing_secret: str) -> bool:
    """Verify Slack's request signing (v0 scheme)."""
    if not signing_secret:
        return False
    if abs(time.time() - int(timestamp)) > 300:
        return False  # Replay attack guard
    base = f"v0:{timestamp}:{request_body.decode()}"
    expected = "v0=" + hmac.new(
        signing_secret.encode(),
        base.encode(),
        hashlib.sha256,
    ).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


def _get_run_workspace_id(run: "Run", db: Session) -> str | None:
    """Resolve workspace_id for a run via its workflow_version → workflow chain."""
    from sqlalchemy import text as _text
    row = db.execute(
        _text("""
            SELECT w.workspace_id
            FROM runs r
            JOIN workflow_versions wv ON r.workflow_version_id = wv.id
            JOIN workflows w ON wv.workflow_id = w.id
            WHERE r.id = :run_id
            LIMIT 1
        """),
        {"run_id": str(run.id)},
    ).fetchone()
    return str(row[0]) if row else None


def _get_slack_signing_secret(run: "Run", db: Session) -> str:
    """Look up the Slack signing secret from the run's workspace credential."""
    from app.models.integration import Integration
    from app.core.crypto import decrypt

    workspace_id = _get_run_workspace_id(run, db)
    if not workspace_id:
        return settings.slack_signing_secret or ""

    row = (
        db.query(Integration)
        .filter(
            Integration.workspace_id == workspace_id,
            Integration.handle == "slack",
        )
        .first()
    )
    if not row or not row.encrypted_credentials:
        return settings.slack_signing_secret or ""
    creds = decrypt(row.encrypted_credentials)
    return creds.get("signing_secret") or settings.slack_signing_secret or ""


@router.post("/slack/interactions")
async def slack_interactions(request: Request, db: Session = Depends(get_db)):
    """
    Handle Slack interactive component payloads.
    Slack sends a URL-encoded body with a 'payload' field containing JSON.
    """
    body = await request.body()
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    signature = request.headers.get("X-Slack-Signature", "")

    # Verify with platform-level signing secret first — before any DB access.
    # This prevents unauthenticated requests from triggering DB reads.
    if not _verify_slack_signature(body, timestamp, signature, settings.slack_signing_secret):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    # Parse payload
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
        log.warning("slack.unknown_run", run_id=run_id_str)
        return {"ok": True}

    # For confirmed requests, optionally re-verify with workspace-level signing secret
    # (workspace-level lookup is safe here because signature is already validated above)
    signing_secret = _get_slack_signing_secret(run, db)
    if signing_secret and signing_secret != settings.slack_signing_secret:
        if not _verify_slack_signature(body, timestamp, signature, signing_secret):
            raise HTTPException(status_code=401, detail="Invalid Slack signature")

    block_id = run.current_block_id or ""
    approver = payload.get("user", {}).get("name", "slack-user")

    if run.status == "paused":
        # Atomic CAS: only the first concurrent Slack click wins.
        # Merge the decision into state and flip status to 'pending' in one statement.
        from sqlalchemy import text as _text
        state = dict(run.state or {})
        state[f"__approval_{block_id}"] = decision
        state[f"__approver_{block_id}"] = approver
        cas_result = db.execute(
            _text(
                "UPDATE runs SET status='pending', paused_at=NULL, state=:state::jsonb "
                "WHERE id=:id AND status='paused' "
                "RETURNING id"
            ),
            {"state": json.dumps(state), "id": run_id_str},
        ).fetchone()

        if cas_result:
            # Write the event and enqueue only if we won the CAS.
            db.add(RunEvent(
                run_id=run_id_str,
                block_id=block_id,
                kind="approval_received",
                payload={"decision": decision, "approver": approver, "source": "slack"},
            ))
            db.commit()
            try:
                _enqueue_run(run_id_str)
            except Exception:
                log.error("slack.redis_enqueue_failed", run_id=run_id_str)
            log.info("run.approval_gate", run_id=run_id_str, decision=decision, approver=approver)
        else:
            # Duplicate click — run already resumed, just ack to Slack.
            db.commit()
            log.info("run.duplicate_approval_ignored", run_id=run_id_str, decision=decision)
    else:
        # Post-run feedback — record verdict, do not re-queue.
        db.add(RunEvent(
            run_id=run_id_str,
            block_id=block_id,
            kind="approval_received",
            payload={"decision": decision, "approver": approver, "source": "slack"},
        ))
        db.commit()
        log.info("run.post_run_verdict", run_id=run_id_str, decision=decision, approver=approver)

    # Update the Slack message to replace buttons with the decision stamp
    msg_container = payload.get("container", {})
    msg_channel = msg_container.get("channel_id") or payload.get("channel", {}).get("id")
    msg_ts = msg_container.get("message_ts") or payload.get("message", {}).get("ts")
    if msg_channel and msg_ts:
        try:
            from app.runtime.integrations.slack import update_approval_message
            from app.models.integration import Integration
            from app.core.crypto import decrypt
            workspace_id = _get_run_workspace_id(run, db)
            if workspace_id:
                slack_row = db.query(Integration).filter(
                    Integration.workspace_id == workspace_id,
                    Integration.handle == "slack",
                ).first()
                if slack_row and slack_row.encrypted_credentials:
                    creds = decrypt(slack_row.encrypted_credentials)
                    slack_token = creds.get("token") or creds.get("bot_token", "")
                    update_approval_message(slack_token, msg_channel, msg_ts, decision, approver)
        except Exception as e:
            log.warning("slack.update_message_failed", error=str(e))

    return {"ok": True}



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


# ── GitHub webhook ────────────────────────────────────────────────────────────

def _verify_github_signature(body: bytes, signature: str) -> bool:
    secret = settings.github_webhook_secret
    if not secret:
        return False  # Reject: no secret configured — set GITHUB_WEBHOOK_SECRET
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


def _repo_from_payload(payload: dict[str, Any]) -> dict[str, Any]:
    repo = payload.get("repository") or {}
    return {
        "id": repo.get("id"),
        "full_name": repo.get("full_name", ""),
        "name": repo.get("name", ""),
        "owner": (repo.get("owner") or {}).get("login", ""),
        "default_branch": repo.get("default_branch", "main"),
        "clone_url": repo.get("clone_url", ""),
    }


def _normalize_github_pr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    pr = payload.get("pull_request") or {}
    action = payload.get("action", "")
    return {
        "event_type": "github_pr_merged" if (action == "closed" and pr.get("merged")) else f"github_pr_{action}",
        "action": action,
        "repo": _repo_from_payload(payload),
        "pr": {
            "number": pr.get("number"),
            "title": pr.get("title", ""),
            "body": pr.get("body") or "",
            "url": pr.get("html_url", ""),
            "author": (pr.get("user") or {}).get("login", ""),
            "head_branch": (pr.get("head") or {}).get("ref", ""),
            "base_branch": (pr.get("base") or {}).get("ref", "main"),
            "merged": pr.get("merged", False),
            "draft": pr.get("draft", False),
            "labels": [l.get("name") for l in pr.get("labels", []) if l.get("name")],
            "requested_reviewers": [(r.get("login") or r.get("name", "")) for r in pr.get("requested_reviewers", [])],
        },
        "sender": {"login": (payload.get("sender") or {}).get("login", "")},
    }


def _normalize_github_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    commits = payload.get("commits") or []
    return {
        "event_type": "github_push",
        "action": "push",
        "repo": _repo_from_payload(payload),
        "push": {
            "ref": payload.get("ref", ""),
            "branch": payload.get("ref", "").removeprefix("refs/heads/"),
            "before": payload.get("before", ""),
            "after": payload.get("after", ""),
            "pusher": (payload.get("pusher") or {}).get("name", ""),
            "commits": [{"id": c.get("id", ""), "message": c.get("message", ""), "author": (c.get("author") or {}).get("name", "")} for c in commits[:10]],
            "forced": payload.get("forced", False),
        },
        "sender": {"login": (payload.get("sender") or {}).get("login", "")},
    }


def _normalize_github_issue_opened_payload(payload: dict[str, Any]) -> dict[str, Any]:
    issue = payload.get("issue") or {}
    return {
        "event_type": "github_issue_opened",
        "action": "opened",
        "repo": _repo_from_payload(payload),
        "issue": {
            "id": issue.get("id"),
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "body": issue.get("body") or "",
            "url": issue.get("html_url", ""),
            "author": (issue.get("user") or {}).get("login", ""),
            "labels": [l.get("name") for l in issue.get("labels", []) if l.get("name")],
        },
        "sender": {"login": (payload.get("sender") or {}).get("login", "")},
    }


def _normalize_github_issue_comment_payload(payload: dict[str, Any]) -> dict[str, Any]:
    issue = payload.get("issue") or {}
    comment = payload.get("comment") or {}
    return {
        "event_type": "github_issue_comment",
        "action": payload.get("action", ""),
        "repo": _repo_from_payload(payload),
        "issue": {
            "number": issue.get("number"),
            "title": issue.get("title", ""),
            "url": issue.get("html_url", ""),
            "author": (issue.get("user") or {}).get("login", ""),
            "labels": [l.get("name") for l in issue.get("labels", []) if l.get("name")],
        },
        "comment": {
            "id": comment.get("id"),
            "body": comment.get("body") or "",
            "url": comment.get("html_url", ""),
            "author": (comment.get("user") or {}).get("login", ""),
        },
        "sender": {"login": (payload.get("sender") or {}).get("login", "")},
    }


def _normalize_github_workflow_run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    run = payload.get("workflow_run") or {}
    return {
        "event_type": "github_workflow_run",
        "action": payload.get("action", ""),
        "repo": _repo_from_payload(payload),
        "workflow_run": {
            "id": run.get("id"),
            "name": run.get("name", ""),
            "status": run.get("status", ""),
            "conclusion": run.get("conclusion", ""),
            "branch": run.get("head_branch", ""),
            "url": run.get("html_url", ""),
            "workflow_id": run.get("workflow_id"),
        },
        "sender": {"login": (payload.get("sender") or {}).get("login", "")},
    }


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


def _build_state(normalized: dict[str, Any], *keys: str) -> dict[str, Any]:
    """Merge repo fields into each state key and attach the full trigger payload."""
    state: dict[str, Any] = {"github_trigger": normalized}
    for key in keys:
        state[key] = {**normalized.get(key, {}), **normalized["repo"]}
    return state


# (github_event, action_predicate, normalizer, internal_event_type, state_keys)
_GITHUB_DISPATCH = [
    ("issues",        lambda a, p: a == "labeled",                                                    _normalize_github_issue_labeled_payload,  "github_issue_labeled",       ("github_issue",)),
    ("issues",        lambda a, p: a == "opened",                                                     _normalize_github_issue_opened_payload,   "github_issue_opened",        ("github_issue",)),
    ("pull_request",  lambda a, p: a in ("opened", "synchronize", "reopened"),                        _normalize_github_pr_payload,             "github_pr_opened",           ("github_pr",)),
    ("pull_request",  lambda a, p: a == "closed" and (p.get("pull_request") or {}).get("merged"),     _normalize_github_pr_payload,             "github_pr_merged",           ("github_pr",)),
    ("pull_request",  lambda a, p: a == "review_requested",                                           _normalize_github_pr_payload,             "github_pr_review_requested", ("github_pr",)),
    ("push",          lambda a, p: not p.get("ref", "").startswith("refs/tags/"),                     _normalize_github_push_payload,           "github_push",                ("github_push",)),
    ("issue_comment", lambda a, p: a == "created",                                                    _normalize_github_issue_comment_payload,  "github_issue_comment",       ("github_comment", "github_issue")),
    ("workflow_run",  lambda a, p: a == "completed",                                                  _normalize_github_workflow_run_payload,   "github_workflow_run",        ("github_workflow_run",)),
]


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
        # No allowlist configured — pass through. The webhook secret + workspace_id
        # URL scoping already constrain which events reach this handler. Requiring
        # an allowlist when none is set would silently block all YAML-installed
        # workflows that don't have repo_allowlist set in their trigger block.
        return True
    return incoming_repo in allowlist


def _trigger_github_workflows(
    db: Session, event_type: str, normalized: dict[str, Any], initial_state: dict[str, Any],
    workspace_id: str | None = None,
) -> list[str]:
    """Route an incoming GitHub event to all matching workflow versions."""
    query = db.query(WorkflowVersion).join(Workflow, Workflow.current_version_id == WorkflowVersion.id)
    if workspace_id:
        query = query.filter(Workflow.workspace_id == workspace_id)
    versions = query.all()

    incoming_repo = (normalized.get("repo") or {}).get("full_name", "")
    incoming_label = normalized.get("label", "")
    issue_labels = (normalized.get("issue") or {}).get("labels", [])

    queued: list[str] = []
    queued_runs: list[Run] = []
    for version in versions:
        nodes = version.graph.get("nodes", [])
        matched = None
        for node in nodes:
            data = node.get("data", {})
            if data.get("type") != "trigger":
                continue
            config = data.get("config", {})
            trigger_event = config.get("event_type", "")
            if trigger_event != event_type:
                continue
            strict = str(config.get("enforcement") or "strict").strip() != "permissive"
            if not _repo_matches(config, incoming_repo, strict):
                continue
            # Label matching only applies to issue-labeled events
            if event_type == "github_issue_labeled" and not _labels_match(config, incoming_label, issue_labels, strict):
                continue
            matched = node
            break

        if not matched:
            continue

        wf_obj = getattr(version, "workflow", None)
        wf_id = str(getattr(wf_obj, "id", "unknown"))
        ws_id = str(getattr(wf_obj, "workspace_id", "unknown"))

        run_state = enrich_run_state_contract(
            {**initial_state, "__triggered_by": f"github:{event_type}"},
            source=f"github:{event_type}",
            trigger_provider="github",
            workflow_id=wf_id,
            workspace_id=ws_id,
            max_turns=20,
        )
        try:
            run_state = validate_run_start_inputs(run_state)
        except InputContractError as err:
            log.warning("github.input_contract_failed", event_type=event_type, error=str(err))
            continue

        run = Run(
            workflow_version_id=version.id,
            workspace_id=wf_obj.workspace_id,
            triggered_by=f"github:{event_type}",
            status="pending",
            state=run_state,
        )
        db.add(run)
        queued_runs.append(run)

    if not queued_runs:
        return []

    # Single commit for all matching runs.
    db.flush()
    db.commit()

    r = _redis()
    for run in queued_runs:
        try:
            _enqueue_run(str(run.id))
            queued.append(str(run.id))
            log.info("github.triggered", event_type=event_type, repo=incoming_repo, run_id=str(run.id))
        except Exception as _enqueue_err:
            log.error("github.enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))

    return queued


@router.post("/github/{project_slug}/{workflow_slug}")
async def github_webhook_by_slug(
    project_slug: str,
    workflow_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Slug-addressed GitHub webhook — one URL per agent, human-readable.

    URL: /webhooks/github/{project-slug}/{workflow-slug}
    e.g. /webhooks/github/devops/autopilot-quick

    Auth: HMAC-SHA256 via X-Hub-Signature-256 header (webhook secret stored
    on the workflow's trigger node). No workspace_id cookie needed.
    """
    from app.core.crypto import decrypt as _decrypt

    body = await request.body()

    # Resolve project → workflow by slugs
    project = db.query(Project).filter(Project.slug == project_slug).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.project_id == project.id,
            Workflow.playbook_slug == workflow_slug,
        )
        .first()
    )
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    version = workflow.current_version
    nodes = version.graph.get("nodes", [])
    trigger_node = next(
        (n for n in nodes if n.get("data", {}).get("type") == "trigger"), None
    )
    if not trigger_node:
        raise HTTPException(status_code=400, detail="Workflow has no trigger node")

    trigger_config = trigger_node.get("data", {}).get("config", {})
    raw_secret = trigger_config.get("webhook_secret", "")
    if not raw_secret:
        raise HTTPException(status_code=401, detail="Workflow has no webhook secret configured")

    try:
        webhook_secret = _decrypt(raw_secret)["secret"]
    except Exception:
        webhook_secret = raw_secret

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    if not sig_header or not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    event = request.headers.get("X-GitHub-Event", "unknown")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

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

    from app.routers.workflows import _estimate_turns_for_graph
    try:
        pf = _estimate_turns_for_graph(version.graph or {}, normalized["issue"]["title"], normalized["issue"]["body"] or "", workspace_id=str(workflow.workspace_id), db=db)
        suggested_turns = pf["suggested_max_turns"]
    except Exception:
        suggested_turns = 20

    run_state = enrich_run_state_contract(
        {
            **initial_state,
            "__triggered_by": "github:github_issue",
        },
        source="github:github_issue",
        trigger_provider="github",
        workflow_id=str(workflow.id),
        workspace_id=str(workflow.workspace_id),
        max_turns=suggested_turns,
    )
    try:
        run_state = validate_run_start_inputs(run_state)
    except InputContractError as err:
        raise HTTPException(status_code=422, detail=str(err))

    run = Run(
        workflow_version_id=version.id,
        workspace_id=workflow.workspace_id,
        triggered_by=f"github:github_issue:{normalized['label']}",
        status="pending",
        state=run_state,
        max_turns=suggested_turns,
    )
    db.add(run)
    db.commit()
    try:
        _enqueue_run(str(run.id))
    except Exception as _enqueue_err:
        log.error("github.slug_enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))
        raise HTTPException(status_code=503, detail="Webhook received but queue is unavailable")
    log.info("github.slug_triggered", project_slug=project_slug, workflow_slug=workflow_slug, run_id=str(run.id))
    return {"ok": True, "queued": 1, "run_ids": [str(run.id)], "label": normalized["label"], "repo": normalized["repo"]["full_name"]}


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
    action = ""

    try:
        payload = json.loads(body)
        action = payload.get("action", "")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    for (gh_event, matches, normalizer, event_type, state_keys) in _GITHUB_DISPATCH:
        if event == gh_event and matches(action, payload):
            normalized = normalizer(payload)
            initial_state = _build_state(normalized, *state_keys)
            queued = _trigger_github_workflows(db, event_type, normalized, initial_state, workspace_id)
            return {"ok": True, "queued": len(queued), "run_ids": queued, "event_type": event_type, "repo": normalized["repo"]["full_name"]}

    return {"ok": True, "queued": 0, "reason": f"event {event}/{action} not handled"}





# ── Clerk webhook — user.created ──────────────────────────────────────────────

import base64 as _base64
import secrets as _secrets
import uuid as _uuid
from datetime import datetime as _dt, timezone as _tz
from sqlalchemy import text as _text


def _verify_clerk_signature(request_body: bytes, headers: dict) -> bool:
    """Verify Clerk webhook signature (svix format) using stdlib hmac."""
    secret = settings.clerk_webhook_secret
    if not secret:
        return True  # skip verification in dev (no secret configured)
    # svix signing secret starts with "whsec_" followed by base64
    raw_secret = _base64.b64decode(secret.removeprefix("whsec_"))
    svix_id        = headers.get("svix-id", "")
    svix_timestamp = headers.get("svix-timestamp", "")
    svix_signature = headers.get("svix-signature", "")
    signed = f"{svix_id}.{svix_timestamp}.{request_body.decode()}"
    expected = _base64.b64encode(
        hmac.new(raw_secret, signed.encode(), hashlib.sha256).digest()
    ).decode()
    # svix-signature may be "v1,<sig>" — compare just the hash part
    for part in svix_signature.split(" "):
        if part.startswith("v1,") and hmac.compare_digest(part[3:], expected):
            return True
    return False


@router.post("/clerk")
async def clerk_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Handles Clerk user.created events.
    Creates workspace + admin role + Guard config immediately on signup.
    Idempotent — safe to replay.
    """
    body = await request.body()

    if not _verify_clerk_signature(body, dict(request.headers)):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = json.loads(body)
    event_type = payload.get("type")

    if event_type != "user.created":
        return {"ok": True, "skipped": event_type}

    user_id: str = payload["data"]["id"]  # Clerk user ID e.g. user_2abc...

    # Idempotency — skip if workspace already exists for this user
    existing = db.execute(
        _text("SELECT 1 FROM workspaces WHERE owner_id = :uid LIMIT 1"),
        {"uid": user_id},
    ).fetchone()
    if existing:
        log.info("clerk_webhook.workspace_exists", user_id=user_id)
        return {"ok": True, "skipped": "workspace already exists"}

    now          = _dt.now(_tz.utc)
    workspace_id = _uuid.uuid4()
    invite_code  = _uuid.uuid4().hex[:16]
    token        = _secrets.token_urlsafe(24)

    db.execute(_text("""
        INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
        VALUES (:id, 'Engineering', :owner_id, 'free', true, :now, :now)
        ON CONFLICT DO NOTHING
    """), {"id": str(workspace_id), "owner_id": user_id, "now": now})

    db.execute(_text("""
        INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
        VALUES (:ws, :uid, 'admin', :now)
        ON CONFLICT DO NOTHING
    """), {"ws": str(workspace_id), "uid": user_id, "now": now})

    db.execute(_text("""
        INSERT INTO guard_config (workspace_id, invite_code, created_at)
        VALUES (:ws, :code, :now)
        ON CONFLICT (workspace_id) DO NOTHING
    """), {"ws": str(workspace_id), "code": invite_code, "now": now})

    db.execute(_text("""
        INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
        VALUES (:ws, :uid, :token, true, :now)
        ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
    """), {"ws": str(workspace_id), "uid": user_id, "token": token, "now": now})

    # Seed starter Guard policies (reuse projects.py helper via direct SQL equivalent)
    from app.routers.projects import _seed_starter_policies
    _seed_starter_policies(db, workspace_id, now)

    db.commit()
    log.info("clerk_webhook.workspace_created", user_id=user_id, workspace_id=str(workspace_id))
    return {"ok": True, "workspace_id": str(workspace_id)}
