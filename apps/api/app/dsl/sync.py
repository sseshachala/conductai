"""
Repo sync — read a ``delegator.yml`` (or any path) from the customer's GitHub
repo and turn it into a new WorkflowVersion.

The customer's flow looks like this:

  1. They commit ``delegator.yml`` to their repo (anywhere — root, .delegator/,
     wherever they prefer).
  2. In Delegator, they set ``workflow.source_repo = "owner/repo"`` and
     ``workflow.source_path = "delegator.yml"``.
  3. On demand (``POST /workflows/{id}/sync``) or in response to a push
     webhook, we fetch the file, validate it, and create a new version if the
     content actually changed.

This is the OSS distribution wedge: a customer can manage their workflow
exactly like Terraform, GitHub Actions, or CircleCI config — in their repo,
versioned by git, reviewed in PRs.
"""
from __future__ import annotations

import hashlib
import structlog
from typing import Any

from sqlalchemy.orm import Session

from app.core.crypto import decrypt
from app.dsl.loader import load_workflow_yaml, yaml_to_graph
from app.dsl.schema import WorkflowValidationError
from app.models.integration import Integration
from app.models.workflow import Workflow, WorkflowVersion
from app.runtime.integrations import github

log = structlog.get_logger(__name__)


class SyncError(Exception):
    """Raised when the sync flow can't complete (missing creds, bad YAML, etc.)."""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _split_repo(source_repo: str) -> tuple[str, str]:
    if "/" not in source_repo:
        raise SyncError(f"source_repo must be 'owner/repo', got: {source_repo!r}")
    owner, repo = source_repo.split("/", 1)
    if not owner or not repo:
        raise SyncError(f"source_repo missing owner or repo: {source_repo!r}")
    return owner, repo


def _github_token(db: Session, workspace_id) -> str:
    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "github",
    ).first()
    if not row or not row.encrypted_credentials:
        raise SyncError("No GitHub credentials configured for this workspace")
    creds = decrypt(row.encrypted_credentials)
    token = creds.get("token") or creds.get("api_key")
    if not token:
        raise SyncError("GitHub credentials missing 'token'")
    return token


def fetch_workflow_yaml_from_repo(
    *,
    db: Session,
    workspace_id,
    source_repo: str,
    source_path: str,
    ref: str | None = None,
) -> dict[str, Any]:
    """
    Fetch + validate the YAML referenced by (source_repo, source_path).

    Returns:
        {"yaml": <text>, "sha": <git blob sha>, "ref": <ref or None>}

    Raises SyncError on any failure the caller should surface to the user.
    """
    token = _github_token(db, workspace_id)
    owner, repo = _split_repo(source_repo)

    result = github.read_file(
        token=token, owner=owner, repo=repo, path=source_path, ref=ref
    )
    if not result.get("found"):
        raise SyncError(
            f"{source_repo}:{source_path}"
            + (f"@{ref}" if ref else "")
            + " — file not found"
        )
    if result.get("error"):
        raise SyncError(f"could not read {source_path}: {result['error']}")

    yaml_text = result.get("content") or ""
    if not yaml_text.strip():
        raise SyncError(f"{source_path} is empty")

    # Validate before persisting so we never write a broken version.
    try:
        load_workflow_yaml(yaml_text)
    except WorkflowValidationError as e:
        raise SyncError(f"{source_path} failed validation: {e}") from e

    return {"yaml": yaml_text, "sha": result.get("sha"), "ref": ref}


def sync_workflow_from_repo(
    *,
    db: Session,
    workflow: Workflow,
    ref: str | None = None,
) -> dict[str, Any]:
    """
    Pull the latest YAML for ``workflow`` from its linked repo and, if the
    content has changed, create a new WorkflowVersion + advance
    ``current_version_id``. Idempotent: no-op when the file hasn't changed.

    Returns a status dict for the API response.
    """
    if not workflow.source_repo or not workflow.source_path:
        raise SyncError(
            "Workflow has no repo source configured (set source_repo + source_path)"
        )

    fetched = fetch_workflow_yaml_from_repo(
        db=db,
        workspace_id=workflow.workspace_id,
        source_repo=workflow.source_repo,
        source_path=workflow.source_path,
        ref=ref,
    )
    new_yaml = fetched["yaml"]
    new_hash = _hash(new_yaml)

    # Compare against the current version. If the YAML is byte-for-byte the
    # same, we don't create a new version — the user can re-run the existing
    # one without burning a row.
    current: WorkflowVersion | None = None
    if workflow.current_version_id:
        current = db.query(WorkflowVersion).filter(
            WorkflowVersion.id == workflow.current_version_id
        ).first()

    if current and current.yaml_source and _hash(current.yaml_source) == new_hash:
        return {
            "synced": True,
            "changed": False,
            "version_id": str(current.id),
            "sha": fetched.get("sha"),
        }

    # Parse + project + persist.
    dsl = load_workflow_yaml(new_yaml)
    graph = yaml_to_graph(dsl)

    version = WorkflowVersion(
        workflow_id=workflow.id,
        yaml_source=new_yaml,
        graph=graph,
    )
    db.add(version)
    db.flush()
    workflow.current_version_id = version.id
    db.commit()
    db.refresh(workflow)

    log.info(
        "Synced workflow %s from %s:%s (sha %s)",
        workflow.id, workflow.source_repo, workflow.source_path, fetched.get("sha"),
    )
    return {
        "synced": True,
        "changed": True,
        "version_id": str(version.id),
        "sha": fetched.get("sha"),
    }
