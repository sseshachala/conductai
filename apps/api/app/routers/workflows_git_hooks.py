"""Git-provider webhook helpers for workflow CRUD (split from workflows.py).

Register / deregister / probe GitHub, GitLab and Bitbucket repo webhooks,
plus the shared manual-registration helper used by the webhook endpoints.
"""
import structlog
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.core.auth import audit
from app.models.workflow import WorkflowVersion
from app.routers.playbooks import (
    _GITHUB_WEBHOOK_EVENTS,
    _ALL_GITHUB_EVENTS,
)

log = structlog.get_logger("app.routers.workflows")


def _register_git_webhook(
    token: str,
    repo: str,
    workflow_id: str,
    events: list[str],
    provider: str = "github",
    project_slug: str | None = None,
    secret: str | None = None,
    workspace_id: str | None = None,
    playbook_slug: str | None = None,
) -> tuple[str | None, str | None]:
    """Register a webhook on the git provider. Returns (hook_id, error_message)."""
    from app.core.config import settings

    if provider == "github" and project_slug and playbook_slug:
        # Per-workflow URL: human-readable + unique per workflow.
        # Format: /webhooks/github/{project_slug}/agent-{playbook_slug}-{id_prefix}
        # The "agent-" prefix matches the auto-prefixed workflow name (see
        # name-prefix logic in create_workflow) so name + slug + webhook URL
        # all use the same formula. Applies to ALL github playbooks.
        id_prefix = workflow_id.replace("-", "")[:8]
        webhook_url = f"{settings.api_base_url}/webhooks/github/{project_slug}/agent-{playbook_slug}-{id_prefix}"
    elif provider == "github" and "issues" in events and workspace_id:
        # Fallback: workspace-scoped fan-out URL (no project_slug — should be rare).
        webhook_url = f"{settings.api_base_url}/webhooks/github?workspace_id={workspace_id}"
    else:
        slug_segment = f"{project_slug}/" if project_slug else ""
        webhook_url = f"{settings.api_base_url}/webhooks/inbound/{slug_segment}{workflow_id}"

    if provider == "gitlab":
        return _register_gitlab_webhook(token, repo, webhook_url, events, secret)
    if provider == "bitbucket":
        return _register_bitbucket_webhook(token, repo, webhook_url, events, secret)
    return _register_github_webhook(token, repo, webhook_url, events, secret)


def _register_github_webhook(token: str, repo: str, webhook_url: str, events: list[str], secret: str | None) -> tuple[str | None, str | None]:
    import httpx
    from app.runtime.integrations.github import _github_headers
    owner, repo_name = repo.split("/", 1)
    headers = _github_headers(token)
    hook_config: dict = {"url": webhook_url, "content_type": "json"}
    if secret:
        hook_config["secret"] = secret
    try:
        existing = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}/hooks", headers=headers, timeout=10)
        if existing.status_code == 200:
            for hook in existing.json():
                if hook.get("config", {}).get("url") == webhook_url:
                    return str(hook["id"]), None
        r = httpx.post(
            f"https://api.github.com/repos/{owner}/{repo_name}/hooks",
            headers=headers,
            json={"name": "web", "active": True, "events": events, "config": hook_config},
            timeout=10,
        )
        if r.status_code == 201:
            hook_id = str(r.json()["id"])
            # Post-registration verification — GET hooks back and confirm ours is visible.
            try:
                verify = httpx.get(f"https://api.github.com/repos/{owner}/{repo_name}/hooks", headers=headers, timeout=10)
                if verify.status_code == 200:
                    if not any(str(h.get("id")) == hook_id for h in verify.json() if isinstance(h, dict)):
                        log.warning("github_webhook.verify_missing", hook_id=hook_id, repo=repo)
                        return None, "Registered but hook not visible on GitHub — try again"
                    log.info("github_webhook.verified", hook_id=hook_id, repo=repo, url=webhook_url)
            except Exception as e:
                log.info("github_webhook.verify_error", hook_id=hook_id, error=str(e))
            return hook_id, None
        log.warning("github_webhook.registration_failed", status_code=r.status_code, response=r.text[:300])
        if r.status_code == 403:
            err = "GitHub rejected the request — your token needs the Administration (read & write) permission. Update your GitHub token in Settings → Environments, then click Register again."
        elif r.status_code == 404:
            err = f"Repository '{repo}' not found or your token doesn't have access to it. Check the repo name and token scopes in Settings → Environments."
        elif r.status_code == 422:
            err = "Webhook already exists on this repo for this URL. You may already have this agent installed — check your agents list."
        else:
            err = f"GitHub returned an unexpected error (HTTP {r.status_code}). Check your token permissions in Settings → Environments."
        return None, err
    except Exception as e:
        log.warning("github_webhook.registration_exception", error=str(e))
        return None, str(e)


def _register_gitlab_webhook(token: str, repo: str, webhook_url: str, events: list[str], secret: str | None) -> tuple[str | None, str | None]:
    """Register a webhook on a GitLab project. repo = 'namespace/project'."""
    import httpx
    from urllib.parse import quote
    encoded = quote(repo, safe="")
    headers = {"PRIVATE-TOKEN": token}
    payload: dict = {
        "url": webhook_url,
        "push_events": "push" in events or "push_events" in events,
        "merge_requests_events": any(e in events for e in ("pull_request", "merge_request", "merge_requests_events")),
        "issues_events": any(e in events for e in ("issues", "issues_events")),
        "enable_ssl_verification": True,
    }
    if secret:
        payload["token"] = secret
    try:
        existing = httpx.get(f"https://gitlab.com/api/v4/projects/{encoded}/hooks", headers=headers, timeout=10)
        if existing.status_code == 200:
            for hook in existing.json():
                if hook.get("url") == webhook_url:
                    return str(hook["id"]), None
        r = httpx.post(f"https://gitlab.com/api/v4/projects/{encoded}/hooks", headers=headers, json=payload, timeout=10)
        if r.status_code == 201:
            return str(r.json()["id"]), None
        err = f"GitLab returned {r.status_code}: {r.text[:300]}"
        log.warning("gitlab_webhook.registration_failed", error=err)
        return None, err
    except Exception as e:
        log.warning("gitlab_webhook.registration_exception", error=str(e))
        return None, str(e)


def _register_bitbucket_webhook(token: str, repo: str, webhook_url: str, events: list[str], secret: str | None) -> tuple[str | None, str | None]:
    """Register a webhook on a Bitbucket repository. repo = 'workspace/repo_slug'."""
    import httpx
    workspace_slug, repo_slug = repo.split("/", 1)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    # Map generic event names to Bitbucket event keys
    bb_events = []
    for e in events:
        if e in ("push", "push_events"):
            bb_events.append("repo:push")
        elif e in ("pull_request", "merge_request"):
            bb_events += ["pullrequest:created", "pullrequest:updated", "pullrequest:fulfilled"]
        elif e in ("issues",):
            bb_events += ["issue:created", "issue:updated"]
    if not bb_events:
        bb_events = ["repo:push"]
    payload: dict = {"description": "Conduct AI", "url": webhook_url, "active": True, "events": bb_events}
    if secret:
        payload["secret"] = secret
    try:
        existing = httpx.get(f"https://api.bitbucket.org/2.0/repositories/{workspace_slug}/{repo_slug}/hooks", headers=headers, timeout=10)
        if existing.status_code == 200:
            for hook in existing.json().get("values", []):
                if hook.get("url") == webhook_url:
                    return str(hook["uuid"]), None
        r = httpx.post(f"https://api.bitbucket.org/2.0/repositories/{workspace_slug}/{repo_slug}/hooks", headers=headers, json=payload, timeout=10)
        if r.status_code == 201:
            return str(r.json()["uuid"]), None
        err = f"Bitbucket returned {r.status_code}: {r.text[:300]}"
        log.warning("bitbucket_webhook.registration_failed", error=err)
        return None, err
    except Exception as e:
        log.warning("bitbucket_webhook.registration_exception", error=str(e))
        return None, str(e)


def _deregister_git_webhook(token: str, repo: str, hook_id: str, provider: str = "github") -> None:
    """Delete a previously registered webhook. Best-effort — never raises."""
    import httpx
    try:
        if provider == "gitlab":
            from urllib.parse import quote
            encoded = quote(repo, safe="")
            httpx.delete(f"https://gitlab.com/api/v4/projects/{encoded}/hooks/{hook_id}", headers={"PRIVATE-TOKEN": token}, timeout=10)
        elif provider == "bitbucket":
            workspace_slug, repo_slug = repo.split("/", 1)
            httpx.delete(f"https://api.bitbucket.org/2.0/repositories/{workspace_slug}/{repo_slug}/hooks/{hook_id}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        else:
            owner, repo_name = repo.split("/", 1)
            from app.runtime.integrations.github import _github_headers
            httpx.delete(
                f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
                headers=_github_headers(token),
                timeout=10,
            )
    except Exception as e:
        log.warning("webhook.deregistration_failed", provider=provider, error=str(e))


def _deregister_github_webhook(token: str, repo: str, hook_id: str) -> None:
    _deregister_git_webhook(token, repo, hook_id, provider="github")


def _github_hook_exists(token: str, repo: str, hook_id: str) -> bool:
    """Return True if the hook still exists on GitHub, False if 404 or error."""
    import httpx
    from app.runtime.integrations.github import _github_headers
    try:
        owner, repo_name = repo.split("/", 1)
        r = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
            headers=_github_headers(token),
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


# ── Manual webhook registration ───────────────────────────────────────────────

def _do_register_workflow_webhook(workflow, workspace_id: str, db: Session) -> str | None:
    """Core webhook registration logic. Returns None on success, error message string on failure.
    Used by both POST /{id}/webhook (raises on error) and create_workflow (soft fail).
    """
    if not workflow.github_hook_repo:
        return "No repository configured"
    if not workflow.current_version_id:
        return "Workflow has no version"
    playbook_slug = workflow.playbook_slug or ""
    if playbook_slug not in _GITHUB_WEBHOOK_EVENTS:
        return None  # Not a webhook-using playbook — silently skip

    import secrets as _secrets
    from app.routers.credentials import _git_token
    from app.core.crypto import encrypt as _encrypt
    from sqlalchemy.orm.attributes import flag_modified
    from app.core.config import settings as _settings

    try:
        token, provider = _git_token(str(workspace_id), db, str(workflow.environment_id) if workflow.environment_id else None)
    except HTTPException as e:
        return f"Credential error: {e.detail}"
    except Exception as e:
        return f"Token fetch failed: {e}"

    repo = workflow.github_hook_repo

    # DB-level dedup REMOVED — it copied stale hook_ids without verifying GitHub state.
    # _register_github_webhook does its own GitHub-side dedup: GET /hooks, reuse if URL matches, else POST.
    # Clear our cached hook_id so we don't try to deregister a (possibly stale) hook.
    if workflow.github_hook_id:
        workflow.github_hook_id = None
        db.commit()

    project_slug: str | None = None
    if workflow.project_id:
        from app.models.project import Project as _Project
        proj = db.query(_Project).filter(_Project.id == workflow.project_id).first()
        if proj:
            project_slug = proj.slug

    webhook_secret = _settings.github_webhook_secret or _secrets.token_hex(32)
    hook_id, error = _register_git_webhook(
        token, repo, str(workflow.id),
        _ALL_GITHUB_EVENTS if provider == "github" else _GITHUB_WEBHOOK_EVENTS[playbook_slug],
        provider=provider,
        project_slug=project_slug,
        secret=webhook_secret,
        workspace_id=str(workspace_id),
        playbook_slug=playbook_slug,
    )
    if not hook_id:
        return error or "Webhook registration failed"

    workflow.github_hook_id = hook_id
    version = db.query(WorkflowVersion).filter(WorkflowVersion.id == workflow.current_version_id).first()
    if version:
        encrypted_secret = _encrypt({"secret": webhook_secret})
        graph = version.graph
        for node in graph.get("nodes", []):
            if node.get("data", {}).get("type") == "trigger":
                node["data"].setdefault("config", {})["webhook_secret"] = encrypted_secret
                node["data"]["config"]["git_provider"] = provider
                node["data"]["config"]["repo_allowlist"] = repo
        version.graph = graph
        flag_modified(version, "graph")
    db.commit()
    audit(db, workspace_id, "workflow.webhook_registered",
          resource_type="workflow", resource_id=str(workflow.id),
          metadata={"repo": repo})
    return None
