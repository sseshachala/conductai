"""
Playbook catalog + submission scores.

Catalog endpoints (prefix /workflows — same URLs as before the split):
  GET  /workflows/playbooks              — list all playbooks from registry
  GET  /workflows/playbooks/{slug}       — playbook detail + YAML source
  GET  /workflows/conflict-check         — pre-install conflict detection

Submission endpoints (prefix /playbooks):
  POST  /playbooks/submit                — community YAML submission (auth or reCAPTCHA)
  GET   /playbooks/submissions           — list rows, filterable by ?status=
  GET   /playbooks/{slug}/score          — latest row for a slug (404 if none)
  PATCH /playbooks/{slug}/submission     — update status (promoted | needs_work | pending)
"""
from datetime import datetime, timezone
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.playbook_submission import PlaybookSubmission
from app.models.workflow import Workflow

# ── Playbook registry ─────────────────────────────────────────────────────────


def _load_registry() -> dict:
    import yaml as _yaml
    from pathlib import Path
    path = Path(__file__).parent.parent.parent / "playbooks" / "registry.yaml"
    return _yaml.safe_load(path.read_text())


_REGISTRY = _load_registry()
_PLAYBOOKS = _REGISTRY["playbooks"]

_TEMPLATE_PLAYBOOKS: dict[str, str] = {slug: meta["file"] for slug, meta in _PLAYBOOKS.items()}
_PLAYBOOK_META: dict[str, dict] = {
    slug: {k: v for k, v in meta.items() if k != "file" and k != "github_events"}
    for slug, meta in _PLAYBOOKS.items()
}
_GITHUB_WEBHOOK_EVENTS: dict[str, list[str]] = {
    slug: meta["github_events"]
    for slug, meta in _PLAYBOOKS.items()
    if "github_events" in meta
}
_ALL_GITHUB_EVENTS: list[str] = _REGISTRY.get("all_github_events", [])


# ── Catalog router (mounted under /workflows to preserve existing URLs) ───────

catalog_router = APIRouter(prefix="/workflows", tags=["workflows"])


@catalog_router.get("/playbooks")
def list_playbooks(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_workspace_id: str | None = Header(default=None),
):
    entries = [
        {
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "icon": _PLAYBOOK_META[slug]["icon"],
            "description": _PLAYBOOK_META[slug]["description"],
            "tags": _PLAYBOOK_META[slug]["tags"],
            "featured": _PLAYBOOK_META[slug]["featured"],
            "category": _PLAYBOOK_META[slug].get("category", "Other"),
            "source": "builtin",
        }
        for slug in _TEMPLATE_PLAYBOOKS
        if slug in _PLAYBOOK_META
    ]
    # Append user-submitted templates when workspace context is available
    if x_workspace_id:
        db_playbooks = (
            db.query(Workflow)
            .filter(
                Workflow.workspace_id == x_workspace_id,
                Workflow.is_template == True,  # noqa: E712
            )
            .all()
        )
        for wf in db_playbooks:
            entries.append(
                {
                    "slug": wf.playbook_slug or str(wf.id),
                    "name": wf.name,
                    "source": "user",
                    "icon": "\U0001f4c4",
                    "category": "custom",
                    "tags": [],
                    "featured": False,
                    "description": "",
                }
            )
    return entries


@catalog_router.get("/playbooks/{slug}")
def get_playbook(slug: str):
    import pathlib
    import yaml as _yaml

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


@catalog_router.get("/conflict-check")
def conflict_check(
    template: str,
    repo: str,
    trigger_label: str = "",
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    """
    Check for conflicts when installing a playbook on a repo.

    Conflict rules:
    - ISSUES_LABELED templates (autopilot variants): conflict = same repo + same label
      -> 3 agents on same repo with different labels is valid
    - PULL_REQUEST templates (pr-reviewer, security-scanner, copilot-reviewer): never conflict
      -> they complement each other, all run independently on PR open
    - SINGLE_TRIGGER templates (issue-triage, ci-notify, release-notes): conflict = same repo
      -> only one instance makes sense
    """
    # Pull-request playbooks never conflict — they complement each other
    _PR_TEMPLATES = {"pr_reviewer", "copilot_reviewer", "security_scanner"}
    if template in _PR_TEMPLATES:
        return {"conflicts": [], "conflict_type": None}

    # Issues-labeled playbooks: conflict only on same label
    _ISSUES_LABELED = {"autopilot_full", "autopilot_approved"}

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


# ── User-submitted playbook (stored in DB as is_template=True) ────────────────

class UserPlaybookSubmitBody(BaseModel):
    yaml: str


class UserPlaybookOut(BaseModel):
    id: str
    slug: str
    name: str


@catalog_router.post("/playbooks/submit", response_model=UserPlaybookOut, status_code=201)
def submit_user_playbook(
    body: UserPlaybookSubmitBody,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    current_user=Depends(require_permission("platform.marketplace.install")),
):
    """
    Store a user-submitted YAML playbook in the workflows table as is_template=True.
    Returns 422 if the YAML is invalid per the DSL, 409 if the slug already exists
    for this workspace.
    """
    import yaml as _yaml
    from app.dsl.loader import load_workflow_yaml

    # 1. Parse
    try:
        parsed = _yaml.safe_load(body.yaml)
    except _yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"YAML parse error: {exc}")

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=422, detail="YAML must be a mapping at the top level")

    # 2. Validate via DSL
    try:
        load_workflow_yaml(body.yaml)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 3. Derive slug
    raw_slug = parsed.get("slug") or parsed.get("name", "")
    slug = raw_slug.lower().replace(" ", "-")[:64]
    if not slug:
        slug = "user-playbook"

    # 4. Conflict check
    existing = (
        db.query(Workflow)
        .filter(
            Workflow.workspace_id == workspace_id,
            Workflow.is_template == True,  # noqa: E712
            Workflow.playbook_slug == slug,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A template playbook with slug '{slug}' already exists in this workspace",
        )

    # 5. Insert
    name = parsed.get("name") or slug
    wf = Workflow(
        name=name,
        workspace_id=workspace_id,
        is_template=True,
        source="user",
        playbook_slug=slug,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)

    return UserPlaybookOut(id=str(wf.id), slug=slug, name=wf.name)


# ── Submission / eval-score router ────────────────────────────────────────────

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

_VALID_STATUSES = {"pending", "promoted", "needs_work"}
_RECAPTCHA_VERIFY_URL = "https://www.google.com/recaptcha/api/siteverify"


async def _verify_recaptcha(token: str) -> bool:
    """Return True if the reCAPTCHA v3 token is valid and score >= threshold."""
    if not settings.recaptcha_secret_key:
        return True  # dev mode — skip verification when key not configured
    async with httpx.AsyncClient(timeout=5) as client:
        resp = await client.post(_RECAPTCHA_VERIFY_URL, data={
            "secret": settings.recaptcha_secret_key,
            "response": token,
        })
    data = resp.json()
    return data.get("success") and float(data.get("score", 0)) >= settings.recaptcha_min_score


class PlaybookSubmitBody(BaseModel):
    yaml_content: str
    recaptcha_token: str | None = None  # required for unauthenticated submissions
    submitter_email: str | None = None  # optional, shown in admin queue


class SubmitOut(BaseModel):
    id: str
    slug: str
    status: str
    message: str


class SubmissionOut(BaseModel):
    slug: str
    source: str
    structural_score: int
    quality_score: int
    grade: str
    status: str
    eval_run_at: datetime
    notes: str | None = None

    class Config:
        from_attributes = True


class SubmissionPatch(BaseModel):
    status: str  # promoted | needs_work | pending


@router.post("/submit", response_model=SubmitOut, status_code=201)
async def submit_playbook(
    body: PlaybookSubmitBody,
    db: Session = Depends(get_db),
    authorization: Annotated[str | None, Header()] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
):
    """
    Community playbook submission.
    - Logged-in users: Authorization header validates identity (no captcha needed).
    - Anonymous users: recaptcha_token must be provided and score >= threshold.
    """
    from app.core.auth import _verify_clerk_token, _clerk_enabled
    from app.dsl.loader import load_workflow_yaml

    # ── Determine submitter identity ──────────────────────────────────────────
    workspace_id: str | None = None
    submitter_email: str | None = body.submitter_email

    is_authenticated = False
    if authorization and authorization.startswith("Bearer ") and _clerk_enabled():
        claims = _verify_clerk_token(authorization.split(" ", 1)[1])
        if claims:
            is_authenticated = True
            workspace_id = x_workspace_id or claims.get("org_id")

    if not is_authenticated:
        # Anonymous path — require a valid reCAPTCHA token
        if not body.recaptcha_token:
            raise HTTPException(status_code=401, detail="recaptcha_token required for unauthenticated submissions")
        if not await _verify_recaptcha(body.recaptcha_token):
            raise HTTPException(status_code=403, detail="Human verification failed — please try again")

    # ── Validate YAML against the DSL ─────────────────────────────────────────
    try:
        workflow = load_workflow_yaml(body.yaml_content)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"Invalid playbook YAML: {e}")

    slug = getattr(workflow, "name", None) or "community-submission"
    slug = slug.lower().replace(" ", "-")[:64]

    # ── Store in submissions queue ─────────────────────────────────────────────
    now = datetime.now(timezone.utc)
    row = PlaybookSubmission(
        slug=slug,
        source="community",
        structural_score=0,
        quality_score=0,
        grade="pending",
        status="pending",
        eval_run_at=now,
        yaml_content=body.yaml_content,
        submitter_email=submitter_email,
        submitter_workspace_id=workspace_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return SubmitOut(
        id=str(row.id),
        slug=row.slug,
        status=row.status,
        message="Submission received — our team will review it shortly.",
    )


# Static route must come before /{slug}/score to avoid path collision.
@router.get("/submissions", response_model=list[SubmissionOut])
def list_submissions(
    status: str | None = Query(default=None, description="Filter by status: pending | promoted | needs_work"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.marketplace.browse")),
):
    """Return all playbook submission rows, optionally filtered by status."""
    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )
    q = db.query(PlaybookSubmission)
    if status:
        q = q.filter(PlaybookSubmission.status == status)
    return q.order_by(PlaybookSubmission.eval_run_at.desc()).all()


@router.get("/{slug}/score", response_model=SubmissionOut)
def get_playbook_score(
    slug: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.marketplace.browse")),
):
    """Return the most recent eval score for a playbook slug. 404 if no row exists."""
    row = (
        db.query(PlaybookSubmission)
        .filter(PlaybookSubmission.slug == slug)
        .order_by(PlaybookSubmission.eval_run_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No submission found for slug '{slug}'")
    return row


@router.patch("/{slug}/submission", response_model=SubmissionOut)
def patch_submission(
    slug: str,
    body: SubmissionPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    """Update the status of a playbook submission. Admin only."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Must be one of: {sorted(_VALID_STATUSES)}",
        )

    row = (
        db.query(PlaybookSubmission)
        .filter(PlaybookSubmission.slug == slug)
        .order_by(PlaybookSubmission.eval_run_at.desc())
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"No submission found for slug '{slug}'")

    row.status = body.status
    if body.status == "promoted":
        row.promoted_at = datetime.now(timezone.utc)
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row
