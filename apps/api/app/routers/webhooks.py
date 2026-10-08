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

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.project import Project
from app.models.run import Run
from app.models.workflow import Workflow
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract
from app.routers.webhooks_github import (
    _GITHUB_DISPATCH,
    _build_state,
    _labels_match,
    _repo_matches,
    _trigger_github_workflows,
)
from app.routers.webhooks_common import _enqueue_run
from app.routers.webhooks_inbound import router

# Re-exported for callers that import these names from this module.
from app.routers.webhooks_slack import (  # noqa: E402,F401
    _handle_guard_slack_decision,
)
from app.routers.webhooks_github import (  # noqa: E402,F401
    _normalize_github_issue_labeled_payload,
)
from app.routers.webhooks_common import (  # noqa: E402,F401
    _verify_slack_signature,
)

log = structlog.get_logger(__name__)


# ── GitHub webhook ────────────────────────────────────────────────────────────

def _verify_github_signature(body: bytes, signature: str) -> bool:
    secret = settings.github_webhook_secret
    if not secret:
        return False  # Reject: no secret configured — set GITHUB_WEBHOOK_SECRET
    expected = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()  # type: ignore[attr-defined]
    return hmac.compare_digest(expected, signature)


@router.post("/github/{project_slug}/{workflow_slug}")
async def github_webhook_by_slug(
    project_slug: str,
    workflow_slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Per-workflow GitHub webhook — one URL per agent, human-readable.

    URL format: /webhooks/github/{project_slug}/agent-{playbook_slug}-{id_prefix}
    e.g. /webhooks/github/marshal/agent-autopilot-a3f912ab

    The id_prefix (first 8 hex chars of workflow.id) disambiguates multiple
    installs of the same playbook in the same project.

    Auth: HMAC-SHA256 via X-Hub-Signature-256 header against per-workflow
    webhook secret stored on the trigger node. No workspace cookie needed.

    Routes ONLY to this workflow — no fan-out across the workspace.
    """
    from app.core.crypto import decrypt as _decrypt

    body = await request.body()

    project = db.query(Project).filter(Project.slug == project_slug).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Parse "agent-{playbook_slug}-{id_prefix}" — rpartition handles playbook slugs
    # that contain dashes (e.g. "autopilot-approved-a3f912ab"). The "agent-" prefix
    # is mandatory — every workflow registers its webhook with it.
    playbook_part, sep, id_prefix = workflow_slug.rpartition("-")
    if not playbook_part.startswith("agent-"):
        raise HTTPException(status_code=400, detail="Workflow slug must start with 'agent-'")
    playbook_part = playbook_part[len("agent-"):]
    if not sep or not id_prefix:
        raise HTTPException(status_code=400, detail="Invalid workflow slug format")

    candidates = db.query(Workflow).filter(
        Workflow.project_id == project.id,
        Workflow.playbook_slug == playbook_part,
        Workflow.archived_at.is_(None),
    ).all()
    workflow = next(
        (w for w in candidates if str(w.id).replace("-", "").startswith(id_prefix)),
        None,
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
    action = payload.get("action", "")

    for (gh_event, matches, normalizer, event_type, state_keys) in _GITHUB_DISPATCH:
        if event != gh_event or not matches(action, payload):
            continue
        normalized = normalizer(payload)
        initial_state = _build_state(normalized, *state_keys)

        # Check this workflow's trigger matches the event_type + repo + label filters.
        if trigger_config.get("event_type", "") != event_type:
            continue
        strict = str(trigger_config.get("enforcement") or "strict").strip() != "permissive"
        incoming_repo = (normalized.get("repo") or {}).get("full_name", "")
        if not _repo_matches(trigger_config, incoming_repo, strict):
            return {"ok": True, "queued": 0, "reason": f"repo {incoming_repo} not in allowlist"}
        if event_type == "github_issue_labeled":
            incoming_label = normalized.get("label", "")
            issue_labels = (normalized.get("issue") or {}).get("labels", [])
            if not _labels_match(trigger_config, incoming_label, issue_labels, strict):
                return {"ok": True, "queued": 0, "reason": f"label {incoming_label} not matched"}

        run_state = enrich_run_state_contract(
            {**initial_state, "__triggered_by": f"github:{event_type}"},
            source=f"github:{event_type}",
            trigger_provider="github",
            workflow_id=str(workflow.id),
            workspace_id=str(workflow.workspace_id),
            max_turns=20,
        )
        try:
            run_state = validate_run_start_inputs(run_state)
        except InputContractError as err:
            raise HTTPException(status_code=422, detail=str(err))

        run = Run(
            workflow_version_id=version.id,
            workspace_id=workflow.workspace_id,
            triggered_by=f"github:{event_type}",
            status="pending",
            state=run_state,
        )
        db.add(run)
        db.commit()
        try:
            _enqueue_run(str(run.id))
        except Exception as _enqueue_err:
            log.error("github.slug_enqueue_failed", run_id=str(run.id), error=str(_enqueue_err))
            raise HTTPException(status_code=503, detail="Webhook received but queue is unavailable")
        log.info("github.slug_triggered", project_slug=project_slug, workflow_slug=workflow_slug,
                 event_type=event_type, run_id=str(run.id))
        return {"ok": True, "queued": 1, "run_ids": [str(run.id)], "event_type": event_type,
                "repo": incoming_repo}

    return {"ok": True, "queued": 0, "reason": f"event {event}/{action} not handled"}


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

    # 1.1 — Cross-tenant protection: require workspace_id to prevent an attacker
    # whose repo name matches any customer's trigger from firing runs across tenants.
    if not workspace_id:
        raise HTTPException(status_code=400, detail="workspace_id query parameter is required")

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
    # 1.4 — Replay protection: reject webhooks older than 5 minutes
    try:
        if abs(time.time() - int(svix_timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False
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

    if event_type == "organization.created":
        clerk_org_id = data.get("id")
        created_by   = data.get("created_by")
        if not clerk_org_id or not created_by:
            return {"ok": True, "skipped": "missing org_id or created_by"}
        row = db.execute(
            _text("SELECT id FROM workspaces WHERE owner_id = :uid LIMIT 1"),
            {"uid": created_by},
        ).fetchone()
        if not row:
            log.warning("clerk_webhook.no_workspace_for_creator", created_by=created_by)
            return {"ok": True, "skipped": "no workspace found for org creator"}
        db.execute(
            _text("UPDATE workspaces SET clerk_org_id = :org WHERE id = :ws"),
            {"org": clerk_org_id, "ws": str(row.id)},
        )
        db.commit()
        log.info("clerk_webhook.org_linked", clerk_org_id=clerk_org_id, workspace_id=str(row.id))
        return {"ok": True, "linked": str(row.id)}

    if event_type == "organizationMembership.created":
        clerk_org_id = data.get("organization", {}).get("id")
        new_user_id  = data.get("public_user_data", {}).get("user_id")
        member_email = data.get("public_user_data", {}).get("identifier", "")
        clerk_role   = data.get("role", "org:member")
        if not clerk_org_id or not new_user_id:
            return {"ok": True, "skipped": "missing org_id or user_id"}
        workspaces = db.execute(
            _text("SELECT id FROM workspaces WHERE clerk_org_id = :org"),
            {"org": clerk_org_id},
        ).fetchall()
        if not workspaces:
            log.warning("clerk_webhook.no_workspaces_for_org", clerk_org_id=clerk_org_id)
            return {"ok": True, "skipped": "no workspaces linked to this org"}
        now   = _dt.now(_tz.utc)
        token = _secrets.token_urlsafe(24)
        for ws_row in workspaces:
            ws_id = str(ws_row.id)
            # Try to get the intended role from workspace_invites
            invite_role_row = db.execute(
                _text("""
                    SELECT role FROM workspace_invites
                    WHERE workspace_id = :ws AND invited_email = :email
                    AND status = 'pending'
                    ORDER BY created_at DESC LIMIT 1
                """),
                {"ws": ws_id, "email": member_email},
            ).fetchone()
            conduct_role = (
                invite_role_row.role
                if invite_role_row and invite_role_row.role
                else ("admin" if clerk_role == "org:admin" else "developer")
            )
            db.execute(_text("""
                INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
                VALUES (:ws, :uid, :role, :now)
                ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
            """), {"ws": ws_id, "uid": new_user_id, "role": conduct_role, "now": now})
            db.execute(_text("""
                INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
                VALUES (:ws, :uid, :token, true, :now)
                ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
            """), {"ws": ws_id, "uid": new_user_id, "token": token, "now": now})
        db.commit()
        log.info("clerk_webhook.member_added", clerk_org_id=clerk_org_id, user_id=new_user_id,
                 workspaces=[str(r.id) for r in workspaces])
        return {"ok": True, "added_to": len(workspaces)}

    if event_type != "user.created":
        return {"ok": True, "skipped": event_type}

    user_id: str = payload["data"]["id"]  # Clerk user ID e.g. user_2abc...

    # #1712 PR 5 — shared onboarding function so the curl-install path and
    # this webhook use one code path. `provision_workspace_for_user` is
    # idempotent (returns existing id if user already has a workspace).
    from app.modules.onboarding import provision_workspace_for_user
    workspace_id = provision_workspace_for_user(db, user_id)
    db.commit()
    return {"ok": True, "workspace_id": str(workspace_id)}
