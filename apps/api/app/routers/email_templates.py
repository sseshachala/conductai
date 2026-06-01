"""
Email templates CRUD.

GET    /email-templates              — list all templates
GET    /email-templates/{slug}       — get one template
PUT    /email-templates/{slug}       — update subject + html_body (admin only)
POST   /email-templates/{slug}/preview — render with sample/provided variables (admin only)
POST   /email-templates/{slug}/reset   — reset to migration default (admin only)
"""
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role
from app.core.config import settings
from app.core.database import get_db
from app.core.email import render_template, _FALLBACK_TEMPLATES, _ROLE_DESCRIPTIONS, APP_URL
from app.models.email_template import EmailTemplate

router = APIRouter(prefix="/email-templates", tags=["email-templates"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TemplateOut(BaseModel):
    slug: str
    subject: str
    html_body: str
    description: str | None
    variables: list[str] | None
    updated_at: datetime


class TemplateUpdate(BaseModel):
    subject: str
    html_body: str
    description: str | None = None


class PreviewRequest(BaseModel):
    variables: dict = {}  # caller-supplied variable values; missing ones get sample defaults


# ---------------------------------------------------------------------------
# Sample defaults per slug (used when caller doesn't supply all variables)
# ---------------------------------------------------------------------------

_SAMPLE_CONTEXT: dict[str, dict] = {
    "workspace_invite": {
        "workspace_name": "Acme Corp",
        "invited_by_email": "admin@acme.com",
        "role": "editor",
        "role_description": _ROLE_DESCRIPTIONS.get("editor", ""),
        "app_url": APP_URL,
    }
}


def _require_admin(x_admin_secret: str | None = Header(default=None)) -> None:
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TemplateOut])
def list_templates(
    db: Session = Depends(get_db),
    _ws: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "security", "viewer")),
):
    return db.query(EmailTemplate).order_by(EmailTemplate.slug).all()


@router.get("/{slug}", response_model=TemplateOut)
def get_template(
    slug: str,
    db: Session = Depends(get_db),
    _ws: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "security", "viewer")),
):
    row = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    return row


@router.put("/{slug}", response_model=TemplateOut)
def update_template(
    slug: str,
    body: TemplateUpdate,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    row = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
    row.subject = body.subject.strip()
    row.html_body = body.html_body.strip()
    if body.description is not None:
        row.description = body.description
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row


@router.post("/{slug}/preview")
def preview_template(
    slug: str,
    body: PreviewRequest,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    """Render the template with provided variables (fills missing vars with sample defaults)."""
    context = {**_SAMPLE_CONTEXT.get(slug, {}), **body.variables}
    rendered = render_template(slug, context, db=db)
    if not rendered:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found or render failed")
    subject, html = rendered
    return {"slug": slug, "subject": subject, "html": html}


@router.post("/{slug}/reset", response_model=TemplateOut)
def reset_template(
    slug: str,
    db: Session = Depends(get_db),
    _: None = Depends(_require_admin),
):
    """Reset template to the built-in default from _FALLBACK_TEMPLATES."""
    fallback = _FALLBACK_TEMPLATES.get(slug)
    if not fallback:
        raise HTTPException(status_code=404, detail=f"No built-in default for '{slug}'")
    row = db.query(EmailTemplate).filter(EmailTemplate.slug == slug).first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Template '{slug}' not found in DB")
    row.subject = fallback["subject"]
    row.html_body = fallback["html_body"]
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return row
