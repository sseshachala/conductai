"""GitHub webhook payload normalisation + workflow fan-out helpers (split from webhooks.py).
"""
import structlog
from typing import Any
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion
from app.runtime.input_contract import InputContractError, validate_run_start_inputs
from app.runtime.run_contract import enrich_run_state_contract
from app.routers.webhooks_common import (
    _enqueue_run,
    _redis,
)

log = structlog.get_logger("app.routers.webhooks")


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

    # No configured labels — fire if not strict (open trigger), reject if strict
    return not strict


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
