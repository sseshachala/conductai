import structlog
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_workspace_role, audit
from app.core.database import get_db

log = structlog.get_logger(__name__)
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
        log.error("compile.background_failed", error=str(e))
    finally:
        db.close()


@router.get("", response_model=list[WorkflowOut])
def list_workflows(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
    project_id: str | None = None,
):
    # Resolve the correct workspace from the project when the active workspace cookie
    # doesn't match the project's workspace (e.g. user navigated across workspace contexts).
    effective_workspace_id = workspace_id
    if project_id:
        from app.models.project import Project
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj and str(proj.workspace_id) != workspace_id:
            proj_ws = str(proj.workspace_id)
            member = db.execute(
                text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
                {"ws": proj_ws, "uid": user_id},
            ).fetchone()
            if member:
                effective_workspace_id = proj_ws

    q = db.query(Workflow).filter(Workflow.workspace_id == effective_workspace_id)
    if project_id:
        q = q.filter(Workflow.project_id == project_id)
    workflows = q.order_by(Workflow.updated_at.desc()).all()

    if not workflows:
        return []

    # Latest run per workflow across ALL versions (not just current) so editing
    # a workflow doesn't make it appear as "never run".
    from sqlalchemy import func
    workflow_uuids = [wf.id for wf in workflows]
    last_run_by_workflow: dict[str, Run] = {}
    if workflow_uuids:
        rn_col = func.row_number().over(
            partition_by=WorkflowVersion.workflow_id,
            order_by=Run.created_at.desc(),
        ).label("rn")
        subq = (
            db.query(
                WorkflowVersion.workflow_id,
                Run.id.label("run_id"),
                Run.status,
                Run.created_at,
                rn_col,
            )
            .join(Run, Run.workflow_version_id == WorkflowVersion.id)
            .filter(WorkflowVersion.workflow_id.in_(workflow_uuids))
            .subquery()
        )
        rows = db.query(subq).filter(subq.c.rn == 1).all()
        for row in rows:
            last_run_by_workflow[str(row.workflow_id)] = row

    results = []
    for wf in workflows:
        out = WorkflowOut.model_validate(wf)
        last_run = last_run_by_workflow.get(str(wf.id))
        if last_run:
            out.last_run_status = last_run.status
            out.last_run_at = last_run.created_at
        results.append(out)
    return results


FRIENDLY_NAMES_SERVER = {
    "autopilot_quick":    "Autopilot Quick",
    "autopilot_full":     "Autopilot Full",
    "autopilot_approved": "Autopilot + Approval",
    "pr_reviewer":        "PR Reviewer",
    "issue_triage":       "Issue Triage",
    "release_notes":      "Release Notes",
    "ci_notify":          "CI Failure Alert",
    "incident_responder": "Incident Responder",
    "dependency_updater": "Dependency Updater",
    "copilot_reviewer":   "Copilot / AI PR Reviewer",
    "security_scanner":   "Security Scanner",
}

_TEMPLATE_PLAYBOOKS = {
    "autopilot_quick":        "autopilot-quick.yaml",
    "autopilot_full":         "autopilot.yaml",
    "autopilot_approved":     "autopilot-approved.yaml",
    "pr_reviewer":            "pr-reviewer.yaml",
    "ci_notify":              "ci-notify.yaml",
    "incident_responder":     "incident-responder.yaml",
    "dependency_updater":     "dependency-updater.yaml",
    "release_notes":          "release-notes.yaml",
    "issue_triage":           "issue-triage.yaml",
    "copilot_reviewer":       "copilot-reviewer.yaml",
    "security_scanner":       "security-scanner.yaml",
    "security_patch_updater": "security-patch-updater.yaml",
    "flaky_test_detective":   "flaky-test-detective.yaml",
    "release_readiness":      "release-readiness.yaml",
    "postmortem_drafter":     "postmortem-drafter.yaml",
    "docs_drift_detector":    "docs-drift-detector.yaml",
    "terraform_reviewer":     "terraform-reviewer.yaml",
}

_PLAYBOOK_META = {
    "autopilot_quick":       {"icon": "⚡",  "category": "Issue to PR",        "tags": ["github", "code"],                    "featured": True,  "description": "GitHub issue labeled → implement fix → open PR. No test step — CI runs tests on the PR."},
    "autopilot_full":        {"icon": "🤖",  "category": "Issue to PR",        "tags": ["github", "code"],                    "featured": True,  "description": "GitHub issue labeled → implement fix → run tests with retry → open PR."},
    "autopilot_approved":    {"icon": "✋",  "category": "Issue to PR",        "tags": ["github", "code", "approval"],        "featured": True,  "description": "Implement fix → run tests → human approves in Slack → open PR. Nothing ships without a gate."},
    "pr_reviewer":           {"icon": "🔍",  "category": "Code Review",        "tags": ["github", "code-review"],             "featured": True,  "description": "Any PR opened → AI reviews the diff for bugs, security issues, and style → posts a review comment."},
    "copilot_reviewer":      {"icon": "🤖",  "category": "Code Review",        "tags": ["github", "code-review", "approval"], "featured": True,  "description": "PR opened by Copilot/Cursor/Claude Code → AI reviews the diff → human approves before merge. The orchestration layer above your AI coding tool."},
    "security_scanner":      {"icon": "🔒",  "category": "Code Review",        "tags": ["github", "code-review", "code"],     "featured": True,  "description": "PR opened → AI scans for OWASP Top 10, hardcoded secrets, auth bypasses, weak crypto → posts structured security report → creates fix issue for critical findings."},
    "issue_triage":          {"icon": "🏷",  "category": "Issue Triage",       "tags": ["github", "ops"],                     "featured": True,  "description": "New issue opened → AI classifies type and priority → adds labels → posts a clarifying comment if vague."},
    "ci_notify":             {"icon": "🚨",  "category": "CI/CD",              "tags": ["github", "notifications"],           "featured": False, "description": "CI build fails → AI diagnoses the failed step → posts root cause and suggested fix to Slack."},
    "flaky_test_detective":  {"icon": "🔬",  "category": "CI/CD",              "tags": ["github", "ci"],                      "featured": True,  "description": "CI run has repeated failures → AI identifies flaky tests, finds the offending commit, posts a fix recommendation."},
    "release_readiness":     {"icon": "✅",  "category": "Release Management", "tags": ["github", "release"],                 "featured": True,  "description": "Release branch cut → AI checks open blockers, failed CI, pending reviews, and unresolved incidents → posts a go/no-go summary."},
    "release_notes":         {"icon": "📝",  "category": "Release Management", "tags": ["github", "notifications"],           "featured": False, "description": "Git tag pushed → AI reads merged PRs → groups by type → writes CHANGELOG entry → posts to Slack."},
    "incident_responder":    {"icon": "🔥",  "category": "Incidents & Ops",    "tags": ["ops", "notifications"],              "featured": False, "description": "Alert fires → AI correlates recent commits and deploys → posts root cause hypothesis to #incidents."},
    "postmortem_drafter":    {"icon": "📋",  "category": "Incidents & Ops",    "tags": ["ops", "docs"],                       "featured": True,  "description": "Incident resolved → AI reads the timeline, alerts, and commits → drafts a structured postmortem with root cause and action items."},
    "dependency_updater":    {"icon": "📦",  "category": "Security",           "tags": ["github", "ops"],                     "featured": False, "description": "Weekly cron → AI scans for outdated deps → bumps patch/minor versions → opens a single clean PR."},
    "security_patch_updater":{"icon": "🛡️",  "category": "Security",           "tags": ["github", "security", "ops"],         "featured": True,  "description": "Dependabot alert fires → AI applies the security patch → runs tests → opens a PR with CVE reference. No waiting for the weekly cron."},
    "docs_drift_detector":   {"icon": "📖",  "category": "Docs",               "tags": ["github", "docs"],                    "featured": True,  "description": "PR merged → AI checks if related docs, README, or runbooks are out of date → opens a follow-up docs PR or creates an issue."},
    "terraform_reviewer":    {"icon": "🏗️",  "category": "Platform & Infra",   "tags": ["github", "infra", "security"],       "featured": True,  "description": "Terraform plan PR opened → AI reviews for security misconfigs, cost anomalies, and drift from approved patterns → posts structured findings."},
}


# Templates that need a GitHub webhook registered — maps slug → GitHub event list
_GITHUB_WEBHOOK_EVENTS: dict[str, list[str]] = {
    "pr_reviewer":           ["pull_request"],
    "copilot_reviewer":      ["pull_request"],
    "issue_triage":          ["issues"],
    "ci_notify":             ["workflow_run"],
    "release_notes":         ["create"],
    "autopilot_quick":       ["issues"],
    "autopilot_full":        ["issues"],
    "autopilot_approved":    ["issues"],
    "security_scanner":      ["pull_request"],
    "security_patch_updater":["repository_vulnerability_alert", "dependabot_alert"],
    "flaky_test_detective":  ["workflow_run"],
    "release_readiness":     ["create"],
    "docs_drift_detector":   ["pull_request"],
    "terraform_reviewer":    ["pull_request"],
}


def _stamp(workflow) -> None:
    """Set transient fields required by WorkflowDetailOut before returning."""
    if not hasattr(workflow, "webhook_error") or workflow.webhook_error is None:  # type: ignore[attr-defined]
        workflow.webhook_error = None  # type: ignore[attr-defined]
    workflow.github_webhook = (workflow.playbook_slug or "") in _GITHUB_WEBHOOK_EVENTS  # type: ignore[attr-defined]


def _register_git_webhook(
    token: str,
    repo: str,
    workflow_id: str,
    events: list[str],
    provider: str = "github",
    project_slug: str | None = None,
    workflow_slug: str | None = None,
    secret: str | None = None,
    workspace_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Register a webhook on the git provider. Returns (hook_id, error_message)."""
    import httpx
    from app.core.config import settings

    # Prefer slug-addressed URL when both project and workflow slugs are available.
    # Falls back to workspace-scoped URL (legacy) or inbound URL.
    if provider == "github" and "issues" in events and project_slug and workflow_slug:
        webhook_url = f"{settings.api_base_url}/webhooks/github/{project_slug}/{workflow_slug}"
    elif provider == "github" and "issues" in events and workspace_id:
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
    owner, repo_name = repo.split("/", 1)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
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
            return str(r.json()["id"]), None
        log.warning("GitHub webhook registration failed: %s %s", r.status_code, r.text[:300])
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
        log.warning("GitHub webhook registration exception: %s", e)
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
        log.warning("GitLab webhook registration failed: %s", err)
        return None, err
    except Exception as e:
        log.warning("GitLab webhook registration exception: %s", e)
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
        log.warning("Bitbucket webhook registration failed: %s", err)
        return None, err
    except Exception as e:
        log.warning("Bitbucket webhook registration exception: %s", e)
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
            httpx.delete(
                f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                timeout=10,
            )
    except Exception as e:
        log.warning("Webhook deregistration failed (%s): %s", provider, e)


def _deregister_github_webhook(token: str, repo: str, hook_id: str) -> None:
    _deregister_git_webhook(token, repo, hook_id, provider="github")


def _github_hook_exists(token: str, repo: str, hook_id: str) -> bool:
    """Return True if the hook still exists on GitHub, False if 404 or error."""
    import httpx
    try:
        owner, repo_name = repo.split("/", 1)
        r = httpx.get(
            f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
            timeout=10,
        )
        return r.status_code == 200
    except Exception:
        return False


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
            "category": _PLAYBOOK_META[slug].get("category", "Other"),
        }
        for slug in _TEMPLATE_PLAYBOOKS
        if slug in _PLAYBOOK_META
    ]


@router.get("/playbooks/{slug}")
def get_playbook(slug: str):
    import pathlib, yaml as _yaml
    if slug not in _TEMPLATE_PLAYBOOKS or slug not in _PLAYBOOK_META:
        raise HTTPException(status_code=404, detail="Playbook not found")
    meta = _PLAYBOOK_META[slug]
    inputs: dict = {}
    playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / _TEMPLATE_PLAYBOOKS[slug]
    if playbook_path.exists():
        raw = _yaml.safe_load(playbook_path.read_text()) or {}
        inputs = raw.get("inputs", {})
    github_webhook = slug in _GITHUB_WEBHOOK_EVENTS
    return {
        "slug": slug,
        "name": slug.replace("_", " ").title(),
        "icon": meta["icon"],
        "description": meta["description"],
        "tags": meta["tags"],
        "featured": meta["featured"],
        "inputs": inputs,
        # All agents operate on a repo — requires_repo is always True.
        # github_webhook: True → Conduct registers a GitHub webhook automatically.
        # False → caller POSTs to the inbound URL (cron, PagerDuty, etc.) — repo is still needed.
        "requires_repo": True,
        "github_webhook": github_webhook,
        "github_events": _GITHUB_WEBHOOK_EVENTS.get(slug, []),
    }


@router.get("/conflict-check")
def conflict_check(
    template: str,
    repo: str,
    trigger_label: str = "",
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Check for conflicts when installing a playbook on a repo.

    Conflict rules:
    - ISSUES_LABELED templates (autopilot variants): conflict = same repo + same label
      → 3 agents on same repo with different labels is valid
    - PULL_REQUEST templates (pr-reviewer, security-scanner, copilot-reviewer): never conflict
      → they complement each other, all run independently on PR open
    - SINGLE_TRIGGER templates (issue-triage, ci-notify, release-notes): conflict = same repo
      → only one instance makes sense
    """
    # Pull-request playbooks never conflict — they complement each other
    _PR_TEMPLATES = {"pr_reviewer", "copilot_reviewer", "security_scanner"}
    if template in _PR_TEMPLATES:
        return {"conflicts": [], "conflict_type": None}

    # Issues-labeled playbooks: conflict only on same label
    _ISSUES_LABELED = {"autopilot_quick", "autopilot_full", "autopilot_approved", "ai_ready"}

    existing = db.query(Workflow).filter(
        Workflow.workspace_id == workspace_id,
        Workflow.github_hook_repo == repo,
    ).all()

    conflicts = []
    for wf in existing:
        if not wf.current_version:
            continue
        nodes = (wf.current_version.graph or {}).get("nodes", [])
        trigger = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
        if not trigger:
            continue
        cfg = trigger.get("data", {}).get("config", {})

        if template in _ISSUES_LABELED:
            # Only conflict if the existing agent watches the same label
            existing_labels = cfg.get("labels", [])
            if trigger_label and trigger_label in existing_labels:
                conflicts.append({"id": str(wf.id), "name": wf.name, "label": trigger_label})
        else:
            # Single-trigger templates: conflict if same event type on same repo
            existing_event = cfg.get("event_type", "")
            new_event = {
                "issue_triage": "github_issues",
                "ci_notify": "workflow_run",
                "release_notes": "create",
            }.get(template, "")
            if new_event and existing_event == new_event:
                conflicts.append({"id": str(wf.id), "name": wf.name, "label": None})

    conflict_type = "label" if template in _ISSUES_LABELED else "duplicate"
    return {"conflicts": conflicts, "conflict_type": conflict_type if conflicts else None}


@router.post("", response_model=WorkflowDetailOut, status_code=201)
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "editor"))):
    import pathlib

    graph_data = body.graph.model_dump()

    if body.template and body.template in _TEMPLATE_PLAYBOOKS:
        playbook_file = _TEMPLATE_PLAYBOOKS[body.template]
        playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / playbook_file
        if playbook_path.exists():
            dsl_text = playbook_path.read_text()
            # Substitute {{inputs.xxx}} with user-supplied values (or YAML defaults)
            if body.inputs or True:
                import yaml as _yaml, re as _re
                raw = _yaml.safe_load(dsl_text) or {}
                declared = raw.get("inputs", {})
                resolved = {k: body.inputs.get(k, v.get("default", "")) for k, v in declared.items()}
                for key, val in resolved.items():
                    dsl_text = dsl_text.replace(f"{{{{inputs.{key}}}}}", str(val))
            try:
                dsl = load_workflow_yaml(dsl_text)
                graph_data = yaml_to_graph(dsl)
            except Exception as _yaml_err:
                log.error("workflow.yaml_parse_failed", template=body.template, error=str(_yaml_err))
                raise HTTPException(status_code=422, detail=f"Template parse error: {_yaml_err}")

    # Resolve environment: use provided, else find/create Default
    from app.models.environment import Environment
    if body.environment_id:
        resolved_env = db.query(Environment).filter(
            Environment.id == body.environment_id,
            Environment.workspace_id == workspace_id,
        ).first()
    else:
        resolved_env = None
    if not resolved_env:
        resolved_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
            Environment.name == "Default",
        ).first()
    if not resolved_env:
        resolved_env = db.query(Environment).filter(
            Environment.workspace_id == workspace_id,
        ).first()
    if not resolved_env:
        resolved_env = Environment(workspace_id=workspace_id, name="Default")
        db.add(resolved_env)
        db.flush()
    default_env = resolved_env

    # Resolve project_id: use provided, else fall back to workspace's default project
    project_id = body.project_id
    if not project_id:
        from sqlalchemy import text as _text
        row = db.execute(
            _text("SELECT id FROM projects WHERE workspace_id = :ws ORDER BY created_at ASC LIMIT 1"),
            {"ws": workspace_id},
        ).fetchone()
        if row:
            project_id = row.id

    workflow = Workflow(
        workspace_id=workspace_id,
        project_id=project_id,
        name=body.name,
        environment_id=default_env.id,
        playbook_slug=body.template or None,
    )
    db.add(workflow)
    db.flush()

    version = WorkflowVersion(workflow_id=workflow.id, graph=graph_data)
    db.add(version)
    db.flush()

    workflow.current_version_id = version.id
    db.commit()

    # Store the repo — webhook registration is now explicit via POST /{id}/webhook
    if body.repo and not workflow.github_hook_repo:
        workflow.github_hook_repo = body.repo
        db.commit()

    db.refresh(workflow)
    _stamp(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "editor", "viewer"))):
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    _stamp(workflow)
    if workflow.project_id:
        from app.models.project import Project as _Proj
        proj = db.query(_Proj).filter(_Proj.id == workflow.project_id).first()
        if proj:
            workflow.project_slug = proj.slug  # type: ignore[attr-defined]
            workflow.project_name = proj.name  # type: ignore[attr-defined]
    return workflow


@router.put("/{workflow_id}", response_model=WorkflowDetailOut)
def update_workflow(
    workflow_id: UUID,
    body: WorkflowUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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

        # Keep github_hook_repo and github_hook_label in sync with trigger config.
        nodes = graph_dict.get("nodes", [])
        trigger_node = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
        if trigger_node:
            cfg = trigger_node.get("data", {}).get("config", {})
            allowlist_raw = cfg.get("repo_allowlist") or ""
            first_repo = next((r.strip() for r in allowlist_raw.split(",") if r.strip()), None)
            if first_repo and first_repo != workflow.github_hook_repo:
                workflow.github_hook_repo = first_repo
            # labels is a list in the graph config (e.g. ["autopilot-ready"])
            labels_raw = cfg.get("labels") or []
            label = labels_raw[0].strip() if labels_raw else None
            if label != workflow.github_hook_label:
                workflow.github_hook_label = label

        db.commit()
        db.refresh(workflow)

        # Compile in background — doesn't block the save response
        background_tasks.add_task(_run_compiler, version.id, graph_dict)
        _stamp(workflow)
        return workflow

    db.commit()
    db.refresh(workflow)
    audit(db, workspace_id, "workflow.created",
          resource_type="workflow", resource_id=str(workflow.id),
          metadata={"name": workflow.name, "template": body.template})
    _stamp(workflow)
    return workflow


@router.delete("/{workflow_id}", status_code=204)
def delete_workflow(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("admin")),
):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")

    # Deregister git webhook only if no sibling workflow shares this hook_id.
    if workflow.github_hook_id and workflow.github_hook_repo:
        try:
            from app.routers.credentials import _git_token
            token, provider = _git_token(str(workspace_id), db)
            siblings = db.query(Workflow).filter(
                Workflow.workspace_id == workflow.workspace_id,
                Workflow.github_hook_repo == workflow.github_hook_repo,
                Workflow.github_hook_id == workflow.github_hook_id,
                Workflow.id != workflow.id,
            ).count()
            if siblings == 0:
                _deregister_git_webhook(token, workflow.github_hook_repo, workflow.github_hook_id, provider=provider)
            else:
                log.info("webhook.delete_skipped_shared", workflow_id=str(workflow_id), siblings=siblings)
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
    audit(db, workspace_id, "workflow.deleted",
          resource_type="workflow", resource_id=str(workflow_id))


# ── Manual webhook registration ───────────────────────────────────────────────

@router.post("/{workflow_id}/webhook", response_model=WorkflowDetailOut)
def register_workflow_webhook(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """Explicitly register (or re-register) the GitHub webhook for this workflow."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.github_hook_repo:
        raise HTTPException(status_code=400, detail="No repository configured — set repo_allowlist in the trigger block first")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no version — save the canvas first")

    playbook_slug = workflow.playbook_slug or ""
    if playbook_slug not in _GITHUB_WEBHOOK_EVENTS:
        raise HTTPException(status_code=400, detail="This workflow type does not use GitHub webhooks")

    import secrets as _secrets
    import re as _re
    from app.routers.credentials import _git_token
    from app.core.crypto import encrypt as _encrypt
    from sqlalchemy.orm.attributes import flag_modified

    token, provider = _git_token(str(workspace_id), db, str(workflow.environment_id) if workflow.environment_id else None)

    repo = workflow.github_hook_repo
    current_events = set(_GITHUB_WEBHOOK_EVENTS.get(playbook_slug, []))
    current_label = workflow.github_hook_label  # may be None for non-label-filtered agents

    # Conflict check: another workflow on this repo watches the same event type AND the same label.
    # Same label + same events = would fire on identical payloads — reject.
    if current_label:
        label_conflict = db.query(Workflow).filter(
            Workflow.workspace_id == workspace_id,
            Workflow.github_hook_repo == repo,
            Workflow.github_hook_id.isnot(None),
            Workflow.id != workflow_id,
            Workflow.github_hook_label == current_label,
            Workflow.playbook_slug.in_([
                slug for slug, evts in _GITHUB_WEBHOOK_EVENTS.items()
                if set(evts) & current_events
            ]),
        ).first()
        if label_conflict:
            raise HTTPException(
                status_code=409,
                detail=f"Label '{current_label}' is already registered on {repo} by '{label_conflict.name}'. "
                       f"Each agent must watch a unique label on this repo.",
            )

    # Sibling check: another workflow on this repo uses the same event type.
    # Share its hook_id — GitHub only needs one inbound webhook per event type per repo.
    same_event_slugs = [
        slug for slug, evts in _GITHUB_WEBHOOK_EVENTS.items()
        if set(evts) & current_events
    ]
    sibling = db.query(Workflow).filter(
        Workflow.workspace_id == workspace_id,
        Workflow.github_hook_repo == repo,
        Workflow.github_hook_id.isnot(None),
        Workflow.id != workflow_id,
        Workflow.playbook_slug.in_(same_event_slugs),
    ).first()

    if sibling:
        # Verify the sibling's hook still exists on GitHub — it may be stale from a past delete.
        if not _github_hook_exists(token, repo, sibling.github_hook_id):
            log.info("webhook.sibling_stale", sibling_id=str(sibling.id), hook_id=sibling.github_hook_id)
            sibling.github_hook_id = None
            db.commit()
            sibling = None  # fall through to fresh registration

    if sibling:
        # Deregister any stale hook this workflow previously owned (best-effort)
        if workflow.github_hook_id and workflow.github_hook_id != sibling.github_hook_id:
            try:
                _deregister_git_webhook(token, repo, workflow.github_hook_id, provider=provider)
            except Exception as e:
                log.warning("Stale webhook deregistration skipped: %s", e)

        workflow.github_hook_id = sibling.github_hook_id
        db.commit()
        db.refresh(workflow)
        audit(db, workspace_id, "workflow.webhook_shared",
              resource_type="workflow", resource_id=str(workflow_id),
              metadata={"repo": repo, "shared_with": str(sibling.id)})
        _stamp(workflow)
        wf_out = WorkflowDetailOut.model_validate(workflow)
        wf_out.github_hook_id = workflow.github_hook_id
        wf_out.github_hook_repo = repo
        wf_out.github_webhook = True
        wf_out.webhook_error = None
        return JSONResponse(content={
            **wf_out.model_dump(mode="json"),
            "shared": True,
            "shared_with_name": sibling.name,
        })

    # No sibling — deregister any stale hook first, then register fresh
    if workflow.github_hook_id:
        try:
            _deregister_git_webhook(token, repo, workflow.github_hook_id, provider=provider)
        except Exception as e:
            log.warning("Stale webhook deregistration skipped: %s", e)
        workflow.github_hook_id = None
        db.commit()

    project_slug: str | None = None
    if workflow.project_id:
        from app.models.project import Project as _Project
        proj = db.query(_Project).filter(_Project.id == workflow.project_id).first()
        if proj:
            project_slug = _re.sub(r"[^a-z0-9]+", "-", proj.name.lower()).strip("-")

    # Workspace-scoped hooks (/webhooks/github) are verified using the global
    # GITHUB_WEBHOOK_SECRET env var. Per-workflow inbound hooks use a random secret
    # stored encrypted in the trigger node config.
    uses_workspace_url = (provider == "github" and "issues" in _GITHUB_WEBHOOK_EVENTS.get(playbook_slug, []))
    if uses_workspace_url:
        from app.core.config import settings as _settings
        webhook_secret = _settings.github_webhook_secret or _secrets.token_hex(32)
    else:
        webhook_secret = _secrets.token_hex(32)

    hook_id, error = _register_git_webhook(
        token, repo, str(workflow.id),
        _GITHUB_WEBHOOK_EVENTS[playbook_slug],
        provider=provider,
        project_slug=project_slug,
        workflow_slug=workflow.playbook_slug,
        secret=webhook_secret,
        workspace_id=str(workspace_id),
    )
    if not hook_id:
        raise HTTPException(status_code=502, detail=error or "Webhook registration failed")

    workflow.github_hook_id = hook_id

    # Store encrypted secret + provider in trigger node of current version
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
    db.refresh(workflow)
    audit(db, workspace_id, "workflow.webhook_registered",
          resource_type="workflow", resource_id=str(workflow_id),
          metadata={"repo": repo})
    _stamp(workflow)
    return workflow


@router.delete("/{workflow_id}/webhook", status_code=204)
def deregister_workflow_webhook(
    workflow_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """Deregister the GitHub webhook for this workflow."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.github_hook_id:
        raise HTTPException(status_code=400, detail="No webhook registered")

    try:
        from app.routers.credentials import _git_token
        token, provider = _git_token(str(workspace_id), db, str(workflow.environment_id) if workflow.environment_id else None)

        # Only delete from GitHub if no other workflow in this workspace shares the hook
        siblings = db.query(Workflow).filter(
            Workflow.workspace_id == workspace_id,
            Workflow.github_hook_repo == workflow.github_hook_repo,
            Workflow.github_hook_id == workflow.github_hook_id,
            Workflow.id != workflow_id,
        ).count()

        if siblings == 0:
            _deregister_git_webhook(token, workflow.github_hook_repo or "", workflow.github_hook_id, provider=provider)
        else:
            log.info("webhook.deregister_skipped_shared", workflow_id=str(workflow_id), siblings=siblings)
    except Exception as e:
        log.warning("Webhook deregistration error: %s", e)

    workflow.github_hook_id = None
    db.commit()
    audit(db, workspace_id, "workflow.webhook_deregistered",
          resource_type="workflow", resource_id=str(workflow_id),
          metadata={"repo": workflow.github_hook_repo})


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
    _role: str = Depends(require_workspace_role("admin", "editor")),
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


def _estimate_turns_for_graph(graph: dict, issue_title: str = "", issue_body: str = "") -> dict:
    """
    Core turn-budget estimation logic — shared between the preflight HTTP endpoint
    and server-side webhook queueing.

    Makes one cheap Haiku call per agentic brain block and returns:
      { suggested_max_turns, blocks, total_files }
    Falls back to defaults on any error so callers are never blocked.
    """
    import anthropic, json, re
    from app.core.config import settings

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
            f"Issue title: {issue_title}\n"
            f"Issue body: {issue_body}\n\n"
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
            text = resp.content[0].text.strip()
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
    suggested = max(total + 5, 20)

    return {
        "suggested_max_turns": suggested,
        "blocks": block_estimates,
        "total_files": list(dict.fromkeys(all_files)),
    }


@router.post("/{workflow_id}/preflight")
def preflight_workflow(
    workflow_id: UUID,
    body: PreflightRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """
    Estimate the turn budget needed before starting a run.
    Makes a single cheap Claude call per agentic brain block — no tools, pure reasoning.
    Returns suggested_max_turns and a per-block breakdown.
    """
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

    graph = workflow.current_version.graph or {}
    return _estimate_turns_for_graph(graph, body.issue_title, body.issue_body)


@router.post("/{workflow_id}/validate")
def validate_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
def compile_workflow_now(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """Explicitly trigger compilation for the current version."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """
    Replace the workflow definition with the provided YAML.

    Returns the workflow with its new current_version_id. The compiled
    artifacts are produced in the background — the caller doesn't wait.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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
def get_workflow_yaml(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return the YAML source for the workflow's current version.

    Sets ``Content-Disposition`` so curl / browsers / the CLI all save the
    file as ``<projectname>-delegator.yml`` — the same convention the canvas
    suggests and the customer is expected to commit to their repo.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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
def get_workflow_yaml_filename(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return the canonical YAML filename + a suggested ``source_path`` for the
    Settings UI to use as the default when binding the workflow to a repo.
    Keeps the naming convention in one place (``app.dsl.naming``) and lets the
    frontend just read it rather than re-implement the slug.
    """
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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
    _role: str = Depends(require_workspace_role("admin", "editor")),
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
    _role: str = Depends(require_workspace_role("admin", "editor")),
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


@router.post("/{workflow_id}/trigger")
def test_trigger(
    workflow_id: UUID,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """
    Authenticated test trigger. When payload is empty, uses the playbook's
    built-in test_trigger.payload (defined in the YAML). Bypasses webhook
    HMAC — callers authenticate via Clerk JWT instead.
    """
    import pathlib, yaml as _yaml
    import redis as _redis_mod
    from app.core.config import settings as _settings

    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow or not workflow.current_version:
        raise HTTPException(status_code=404, detail="Workflow not found")

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
        pf = _estimate_turns_for_graph(graph, payload.get("title", ""), payload.get("body", ""))
        suggested_turns = pf["suggested_max_turns"]
    except Exception:
        suggested_turns = 20

    run = Run(
        workflow_version_id=version.id,
        triggered_by="manual:test_trigger",
        status="pending",
        state={"_trigger": payload, "__triggered_by": "manual:test_trigger", "__max_turns": suggested_turns},
        max_turns=suggested_turns,
    )
    db.add(run)
    db.flush()
    db.commit()

    r = _redis_mod.from_url(_settings.redis_url, decode_responses=True)
    r.rpush("marshal:runs:queue", str(run.id))

    log.info("workflow.test_triggered", workflow_id=str(workflow_id), run_id=str(run.id), playbook_slug=workflow.playbook_slug)
    return {"ok": True, "run_id": str(run.id), "max_turns": suggested_turns}


class SyncRequest(BaseModel):
    ref: str | None = None  # branch / tag / sha; default = repo default branch


@router.post("/{workflow_id}/sync")
def sync_workflow(
    workflow_id: UUID,
    body: SyncRequest = Body(default=SyncRequest()),
    background_tasks: BackgroundTasks = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """
    Fetch the YAML at ``workflow.source_repo:source_path`` from GitHub,
    validate it, and create a new WorkflowVersion if the content changed.
    No-op when the source matches the current version.
    """
    from app.dsl.sync import SyncError, sync_workflow_from_repo

    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
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
