import structlog
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Body, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_workspace_role, require_permission, audit
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
from app.runtime.model_router import resolve as resolve_model
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates, pricing_note
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract

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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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

    # Batch-fetch project names
    from app.models.project import Project as _ListProject
    project_ids = {wf.project_id for wf in workflows if wf.project_id}
    project_names: dict[str, str] = {}
    if project_ids:
        for proj in db.query(_ListProject).filter(_ListProject.id.in_(project_ids)).all():
            project_names[str(proj.id)] = proj.name

    results = []
    for wf in workflows:
        out = WorkflowOut.model_validate(wf)
        last_run = last_run_by_workflow.get(str(wf.id))
        if last_run:
            out.last_run_status = last_run.status
            out.last_run_at = last_run.created_at
        if wf.project_id:
            out.project_name = project_names.get(str(wf.project_id))
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
    "smoke_test":             "Smoke Test",
    "thirdparty_autopilot_fix": "Third-Party Autopilot Fix",
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
    "thirdparty_autopilot_fix": "thirdparty-autopilot-fix.yaml",
    "smoke_test":             "smoke-test.yaml",
    "factory":               "factory.yaml",
    "security_loop":              "security_loop.yaml",
    "security_autopilot_fix":     "security-autopilot-fix.yaml",
    "bughunter_active_scan":      "bughunter-active-scan.yaml",
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
    "thirdparty_autopilot_fix":{"icon": "🔀", "category": "Issue to PR",        "tags": ["github", "code", "oss"],             "featured": True,  "description": "Issue on any third-party repo → AI forks it, clones the fork, reads the issue, applies the fix, and opens a PR back to upstream. Works on any public repo."},
    "smoke_test":            {"icon": "🏓",  "category": "Testing",            "tags": ["ci", "ops"],                         "featured": False, "description": "Minimal 1-step pipeline ping. Fires a brain block and returns ok. Use for CI gating and worker health checks — completes in under 30s."},
    "factory":               {"icon": "🏭",  "category": "Issue to PR",        "tags": ["github", "code", "tdd", "approval"],  "featured": True,  "description": "GitHub issue → spec (Opus) → architecture + ADR → failing tests → implementation → passing tests → human approval → PR. The full software factory pipeline."},
    "security_loop":              {"icon": "🔐",  "category": "Security",    "tags": ["security", "agentic", "autopilot"],                "featured": True,  "bundled_with": "security-loop-module", "description": "Security Loop Automation — AI agent triages every finding from Security Loop for Claude. Dismisses false positives instantly, escalates real threats, and with Agentic Autopilot opens fix PRs autonomously."},
    "security_autopilot_fix":     {"icon": "🔧",  "category": "Security",    "tags": ["security", "github", "autopilot"],                 "featured": True,  "bundled_with": "security-loop-module", "description": "Security finding → reads affected file → writes targeted patch → opens PR → notifies Slack. Triggered from the Security Loop activity page."},
    "bughunter_active_scan":      {"icon": "🔍",  "category": "Security",    "tags": ["security", "bughunter", "scanning"],               "featured": True,  "description": "Dynamically discovers and runs all Claude-BugHunter hunt-* skills against a target repo. Findings flow into Security Loop + GitHub issues automatically."},
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
    "factory":               ["issues"],
}

# All GitHub events Conduct ever listens to — used when registering a repo webhook
# so GitHub sends everything and we filter in the handler.
_ALL_GITHUB_EVENTS = [
    "issues", "pull_request", "push", "issue_comment",
    "create", "workflow_run", "repository_vulnerability_alert", "dependabot_alert",
    "pull_request_review", "pull_request_review_comment",
]


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
    secret: str | None = None,
    workspace_id: str | None = None,
) -> tuple[str | None, str | None]:
    """Register a webhook on the git provider. Returns (hook_id, error_message)."""
    import httpx
    from app.core.config import settings

    if provider == "github" and "issues" in events and workspace_id:
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
            httpx.delete(
                f"https://api.github.com/repos/{owner}/{repo_name}/hooks/{hook_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"},
                timeout=10,
            )
    except Exception as e:
        log.warning("webhook.deregistration_failed", provider=provider, error=str(e))


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
    yaml_source: str = ""
    playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / _TEMPLATE_PLAYBOOKS[slug]
    blocks: list = []
    if playbook_path.exists():
        yaml_source = playbook_path.read_text()
        raw = _yaml.safe_load(yaml_source) or {}
        inputs = raw.get("inputs", {})
        # Trigger block from the `on:` key (PyYAML parses `on` as True)
        trigger_raw = raw.get(True, {}) or {}
        if trigger_raw:
            event = next(iter(trigger_raw), None)
            blocks.append({
                "id": "_trigger",
                "type": "trigger",
                "label": (event or "trigger").replace(".", " ").replace("_", " ").title(),
                "description": None,
                "integration": (trigger_raw.get(event) or {}).get("integration"),
                "model": None,
            })
        for block_id, block_data in (raw.get("blocks") or {}).items():
            if not isinstance(block_data, dict):
                continue
            desc = block_data.get("description") or ""
            # Trim long descriptions to first non-empty line
            first_line = next((l.strip() for l in desc.splitlines() if l.strip()), None)
            blocks.append({
                "id": block_id,
                "type": block_data.get("type", "tool"),
                "label": block_data.get("label", block_id.replace("_", " ").title()),
                "description": first_line,
                "integration": block_data.get("integration"),
                "model": block_data.get("model"),
            })
    github_webhook = slug in _GITHUB_WEBHOOK_EVENTS
    return {
        "slug": slug,
        "name": slug.replace("_", " ").title(),
        "icon": meta["icon"],
        "description": meta["description"],
        "tags": meta["tags"],
        "featured": meta["featured"],
        "category": meta.get("category", "Other"),
        "inputs": inputs,
        "blocks": blocks,
        "yaml_source": yaml_source,
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
def create_workflow(body: WorkflowCreate, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "developer"))):
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

    # Sync github_hook_repo + github_hook_label from trigger node config (covers
    # both explicit body.repo and YAML-installed workflows where repo comes from
    # the trigger block's repo_allowlist field).
    nodes = graph_data.get("nodes", [])
    trigger_node = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
    if trigger_node:
        cfg = trigger_node.get("data", {}).get("config", {})
        allowlist_raw = cfg.get("repo_allowlist") or body.repo or ""
        first_repo = next((r.strip() for r in str(allowlist_raw).split(",") if r.strip()), None)
        if first_repo:
            workflow.github_hook_repo = first_repo
        labels_raw = cfg.get("labels") or []
        label = labels_raw[0].strip() if labels_raw else None
        if label:
            workflow.github_hook_label = label
    elif body.repo:
        workflow.github_hook_repo = body.repo
    db.commit()

    db.refresh(workflow)
    _stamp(workflow)
    return workflow


@router.get("/{workflow_id}", response_model=WorkflowDetailOut)
def get_workflow(workflow_id: UUID, db: Session = Depends(get_db), workspace_id: str = Depends(get_workspace_id), _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer"))):
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
):
    # SELECT FOR UPDATE — serialise concurrent saves on the same workflow so two
    # editors can't both read, both create a WorkflowVersion, and silently
    # discard each other's changes.  The second writer blocks until the first
    # commits, then reads the refreshed row and applies its edit on top.
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id, Workflow.workspace_id == workspace_id
    ).with_for_update().first()
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
    _: str = Depends(require_permission("platform.workflows.edit")),
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
            log.warning("webhook.deregistration_skipped", workflow_id=str(workflow_id), error=str(e))

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
    _role: str = Depends(require_workspace_role("admin", "developer")),
):
    """Explicitly register (or re-register) the GitHub webhook for this workflow."""
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id, Workflow.workspace_id == workspace_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.github_hook_repo:
        # Try to recover from trigger node config (handles workflows installed before sync fix)
        if workflow.current_version:
            nodes = workflow.current_version.graph.get("nodes", [])
            trigger = next((n for n in nodes if n.get("data", {}).get("type") == "trigger"), None)
            if trigger:
                raw = trigger.get("data", {}).get("config", {}).get("repo_allowlist") or ""
                first = next((r.strip() for r in str(raw).split(",") if r.strip()), None)
                if first:
                    workflow.github_hook_repo = first
                    db.commit()
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

    # One webhook per repo: reuse an existing Conduct hook if one already exists for this repo.
    existing = db.query(Workflow).filter(
        Workflow.workspace_id == workspace_id,
        Workflow.github_hook_repo == repo,
        Workflow.github_hook_id.isnot(None),
        Workflow.id != workflow_id,
    ).first()

    if existing:
        workflow.github_hook_id = existing.github_hook_id
        db.commit()
        db.refresh(workflow)
        _stamp(workflow)
        return workflow

    # No existing hook — deregister any stale one first, then register fresh.
    if workflow.github_hook_id:
        try:
            _deregister_git_webhook(token, repo, workflow.github_hook_id, provider=provider)
        except Exception as e:
            log.warning("webhook.stale_deregistration_skipped", workflow_id=str(workflow_id), error=str(e))
        workflow.github_hook_id = None
        db.commit()

    project_slug: str | None = None
    if workflow.project_id:
        from app.models.project import Project as _Project
        proj = db.query(_Project).filter(_Project.id == workflow.project_id).first()
        if proj:
            project_slug = proj.slug  # use the stored slug, not a runtime derivation

    from app.core.config import settings as _settings
    webhook_secret = _settings.github_webhook_secret or _secrets.token_hex(32)

    hook_id, error = _register_git_webhook(
        token, repo, str(workflow.id),
        _ALL_GITHUB_EVENTS if provider == "github" else _GITHUB_WEBHOOK_EVENTS[playbook_slug],
        provider=provider,
        project_slug=project_slug,
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
        log.warning("webhook.deregistration_error", workflow_id=str(workflow_id), error=str(e))

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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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


def _resolve_preflight_key(workspace_id: str | None, db: Session | None) -> str | None:
    """Resolve ANTHROPIC_API_KEY from workspace vault, fall back to server key."""
    from app.core.config import settings
    if workspace_id and db:
        try:
            from app.models.integration import Integration
            from app.models.environment import Environment as _Env
            from app.core.crypto import decrypt
            default_env = db.query(_Env).filter(
                _Env.workspace_id == workspace_id,
                _Env.name == "Default",
            ).first()
            env_ids = [str(default_env.id)] if default_env else []
            for eid in env_ids:
                rows = db.query(Integration).filter(
                    Integration.workspace_id == workspace_id,
                    Integration.environment_id == eid,
                    Integration.handle.in_(["anthropic", "env_vars"]),
                ).all()
                for row in rows:
                    if not row.encrypted_credentials:
                        continue
                    creds = decrypt(row.encrypted_credentials) or {}
                    key = creds.get("api_key") if row.handle == "anthropic" else (
                        creds.get("ANTHROPIC_API_KEY") or creds.get("anthropic_api_key")
                    )
                    if key:
                        return key
        except Exception:
            pass
    return settings.anthropic_api_key


def _estimate_turns_for_graph(
    graph: dict,
    issue_title: str = "",
    issue_body: str = "",
    min_turns: int = 0,
    workspace_id: str | None = None,
    db: Session | None = None,
) -> dict:
    """
    Core turn-budget estimation logic — shared between the preflight HTTP endpoint
    and server-side webhook queueing.

    Makes one cheap Haiku call per agentic brain block and returns:
      { suggested_max_turns, blocks, total_files }
    Falls back to defaults on any error so callers are never blocked.
    """
    import anthropic, json, re

    nodes = graph.get("nodes", [])
    brain_blocks = [
        n for n in nodes
        if n.get("data", {}).get("type") == "brain"
        and n.get("data", {}).get("isAgentic", False)
    ]

    if not brain_blocks:
        return {"suggested_max_turns": 20, "blocks": [], "total_files": []}

    api_key = _resolve_preflight_key(workspace_id, db)
    client = anthropic.Anthropic(api_key=api_key)
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
    suggested = max(total + 5, 20, min_turns)

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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
    result = _estimate_turns_for_graph(graph, body.issue_title, body.issue_body, min_turns, workspace_id, db)
    result["min_turns"] = min_turns
    return result


@router.post("/{workflow_id}/validate")
def validate_workflow(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    configured_services = {row.service.lower() for row in cred_rows if row.encrypted_credentials}

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

    return {"valid": len(errors) == 0, "errors": errors}


@router.get("/{workflow_id}/estimate")
def estimate_workflow_cost(
    workflow_id: UUID,
    issues: int = 1,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
):
    """
    Estimate token usage and cost for this workflow.
    Uses actual historical run data when available; falls back to static estimates.
    ?issues=N multiplies cost by number of matching GitHub issues.
    Pricing is resolved from the runtime pricing registry.
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
            provider, model, _ = resolve_model(workflow.playbook_slug, routing_pref, explicit_model, explicit_provider)
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
):
    """
    Replace the workflow definition with the provided YAML.

    Returns the workflow with its new current_version_id. The compiled
    artifacts are produced in the background — the caller doesn't wait.
    """
    # SELECT FOR UPDATE — same serialisation as the graph PUT endpoint.
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id, Workflow.workspace_id == workspace_id
    ).with_for_update().first()
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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


class WorkflowTurnSettingsRequest(BaseModel):
    default_max_turns: Optional[int] = None


@router.patch("/{workflow_id}/turn-settings")
def update_turn_settings(
    workflow_id: UUID,
    body: WorkflowTurnSettingsRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer")),
):
    """Persist a default turn budget override for this workflow."""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    workflow.default_max_turns = body.default_max_turns
    db.commit()
    return {"id": str(workflow.id), "default_max_turns": workflow.default_max_turns}


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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
        # min_turns: honour YAML-declared floor and workflow DB override
        yaml_min = 0
        if version.yaml_source:
            try:
                raw_yaml = _yaml.safe_load(version.yaml_source) or {}
                yaml_min = int((raw_yaml.get("inputs", {}).get("min_turns", {}) or {}).get("default", 0))
            except Exception:
                pass
        min_turns = max(yaml_min, workflow.default_max_turns or 0)
        pf = _estimate_turns_for_graph(graph, payload.get("title", ""), payload.get("body", ""), min_turns, workspace_id, db)
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
    _initial_state: dict = {"__triggered_by": "manual:test_trigger", "__max_turns": suggested_turns}
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
    else:
        # Non-GitHub trigger — keep raw payload as _trigger
        _initial_state["_trigger"] = payload

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

    run = Run(
        workflow_version_id=version.id,
        triggered_by="manual:test_trigger",
        status="pending",
        state=_initial_state,
        max_turns=suggested_turns,
    )
    db.add(run)
    db.commit()

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
    _role: str = Depends(require_workspace_role("admin", "developer")),
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
