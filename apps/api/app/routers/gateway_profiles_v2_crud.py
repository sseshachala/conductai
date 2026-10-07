"""Gateway Profile v2 create / import / export / read / update / rate-limit / delete endpoints
(split from gateway_profiles_v2.py).

Owns the shared ``/workspaces`` gateway-profiles-v2 APIRouter. The publish /
rollback / revisions / test endpoints in gateway_profiles_v2.py import
``router`` from here, which keeps the original route registration order.
"""
from __future__ import annotations
from typing import Any
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.auth import require_permission
from app.core.database import get_db
from app.models.gateway_profile import (
    GatewayProfile as GatewayProfileRow,
    GatewayProfileRevision,
    GatewayProfileRateLimit,
)
from app.routers.gateway_profiles_v2_schemas import (
    CreateProfileBody,
    ImportProfileBody,
    ImportProfileOut,
    ProfileOut,
    ProfileRateLimitsBody,
    ProfileRateLimitsOut,
    UpdateWorkingCopyBody,
)
from app.routers.gateway_profiles_v2_helpers import (
    _authorized_workspace_id,
    _generate_unique_cond_code,
    _load_profile,
    _profile_rate_limits_output,
    _strip_credentials,
    _to_output,
    _validate_working_copy,
)

_log = structlog.get_logger("app.routers.gateway_profiles_v2")


router = APIRouter(
    prefix="/workspaces",
    tags=["gateway-profiles-v2"],
)


# ─── Endpoints ────────────────────────────────────────────────────────


@router.post(
    "/{workspace_id}/gateway-profiles-v2",
    response_model=ProfileOut,
    status_code=201,
)
def create_profile(
    workspace_id: str,
    body: CreateProfileBody,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Create a new draft profile.

    ``working_copy`` may be an empty dict; validation only fires on
    publish. This lets admins iterate on the shape without every save
    tripping the capability catalog.

    ``cond_code`` is server-generated and immutable — becomes the
    public routing identifier ``cond-<code>-<alias>`` clients send in
    ``model:``.
    """
    profile = GatewayProfileRow(
        workspace_id=workspace_id,
        environment_id=None,       # v3 doesn't scope profiles to envs
        name=body.name,
        schema_version="2",
        config={},                  # v1 column intentionally empty for v2 rows
        working_copy=body.working_copy or None,
        model_alias=body.working_copy.get("model_alias") if body.working_copy else None,
        cond_code=_generate_unique_cond_code(db, workspace_id),
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


# ─── Import / export ──────────────────────────────────────────────────
#
# Portable JSON round-trip so admins can version-control profile shape
# in their repo and stamp it into any workspace via CLI or UI.
#
# Design decisions locked in the design discussion:
#   Q1: JSON = same shape as ``working_copy`` (also what export emits)
#   Q2: server ALWAYS strips credential_ref on import — one file
#       works across environments without leaking secrets
#   Q3: separate ``/import`` and ``/export`` endpoints (not flags on
#       existing create/get) — cleaner review, distinct behavior
#   Q4: UI uses textarea paste against the same endpoint the CLI hits
#   Q5: symmetric — export strips creds too, so what you export you
#       can re-import cleanly


@router.post(
    "/{workspace_id}/gateway-profiles-v2/import",
    response_model=ImportProfileOut,
    status_code=201,
)
def import_profile(
    workspace_id: str,
    body: ImportProfileBody,
    request: Request,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Create a draft from a portable JSON payload.

    Credentials are ALWAYS stripped — the response's
    ``credential_gaps`` lists every target that needs a vault + handle
    pick, and ``next_url`` links to the editor page for the created
    profile so the admin can finish setup in one click.

    Shape validation is deferred to publish (same as create). This
    lets an admin import a partial JSON, edit it, then publish.
    """
    stripped_wc, gaps = _strip_credentials(body.working_copy)

    # Name resolution: explicit override wins → JSON's own name →
    # fallback to a generic label. Uniqueness within the workspace is
    # enforced by the ``UNIQUE (workspace_id, name)`` DB constraint,
    # which raises IntegrityError we catch to translate to 409.
    name = (
        body.name_override
        or (stripped_wc.get("name") if isinstance(stripped_wc, dict) else None)
        or "imported-profile"
    )
    # Reflect the resolved name back into working_copy so the editor
    # sees a consistent draft (name field + model_alias if present
    # stay in sync).
    if isinstance(stripped_wc, dict):
        stripped_wc["name"] = name

    model_alias = None
    if isinstance(stripped_wc, dict):
        raw_alias = stripped_wc.get("model_alias")
        if isinstance(raw_alias, str):
            model_alias = raw_alias

    profile = GatewayProfileRow(
        workspace_id=workspace_id,
        environment_id=None,
        name=name,
        schema_version="2",
        config={},
        working_copy=stripped_wc,
        model_alias=model_alias,
        cond_code=_generate_unique_cond_code(db, workspace_id),
    )
    try:
        db.add(profile)
        db.commit()
        db.refresh(profile)
    except IntegrityError as exc:  # unique(workspace, name) collision
        db.rollback()
        # Two paths land here:
        #   1. Caller didn't pass name_override → JSON's own name
        #      collided. Suggest name_override.
        #   2. Caller DID pass name_override → their chosen name
        #      collided too. Don't re-suggest name_override (they
        #      already used it); tell them to pick something else.
        if body.name_override:
            message = (
                f"The name {name!r} is already taken in this workspace. "
                f"Pick a different value for ``name_override``."
            )
        else:
            message = (
                f"A profile named {name!r} already exists in this "
                f"workspace. Pass ``name_override`` to import under a "
                f"different name."
            )
        raise HTTPException(
            status_code=409,
            detail={
                "summary": "profile name already exists",
                "errors": [{
                    "path": "name",
                    "message": message,
                    "target_index": None,
                    "type": "conflict",
                }],
            },
        ) from exc

    out = _to_output(db, workspace_id, profile)

    # Absolute URL to the editor page. Uses ``settings.app_url``
    # (the web-app URL, e.g. ``https://app.conductai.ai``) —
    # ``request.base_url`` is the API's own host, which serves
    # ``/gateway/v1/*`` but NOT the ``/proxy/*`` editor routes.
    # Following ``https://api.conductai.ai/proxy/gateway-profiles``
    # 404s; following ``https://app.conductai.ai/proxy/gateway-profiles``
    # opens the editor.
    from app.core.config import settings as _settings
    web_base = (_settings.app_url or "").rstrip("/")
    next_url = (
        f"{web_base}/proxy/gateway-profiles?select={profile.id}"
        if web_base
        else f"/proxy/gateway-profiles?select={profile.id}"
    )

    return ImportProfileOut(
        profile=out,
        credential_gaps=gaps,
        next_url=next_url,
    )


@router.get(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/export",
    response_model=dict[str, Any],
)
def export_profile(
    workspace_id: str,
    profile_id: UUID,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Return a portable JSON snapshot of the profile.

    Prefers the active revision's snapshot (immutable, always has full
    credential_refs pre-strip) over ``working_copy``. Falls back to
    ``working_copy`` for pure-draft profiles.

    Credentials are stripped so the exported JSON is safe to commit to
    a repo and re-import into a different workspace. Round-trip
    behavior: ``export → import`` produces a draft the admin can
    complete via the Save gate's credential pickers.
    """
    profile = _load_profile(db, workspace_id, profile_id)

    seed: dict[str, Any] | None = None
    if profile.active_revision_id is not None:
        revision = (
            db.query(GatewayProfileRevision)
            .filter(
                GatewayProfileRevision.id == profile.active_revision_id,
                GatewayProfileRevision.profile_id == profile_id,
            )
            .one_or_none()
        )
        if revision is not None and isinstance(revision.snapshot, dict):
            seed = revision.snapshot
    if seed is None and isinstance(profile.working_copy, dict):
        seed = profile.working_copy
    if seed is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Profile {profile_id} has no working_copy and no "
                f"published revision — nothing to export."
            ),
        )

    stripped, _gaps = _strip_credentials(seed)
    return stripped


@router.get(
    "/{workspace_id}/gateway-profiles-v2",
    response_model=list[ProfileOut],
)
def list_profiles(
    workspace_id: str,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """List every v2 profile in the workspace."""
    rows = (
        db.query(GatewayProfileRow)
        .filter(
            GatewayProfileRow.workspace_id == workspace_id,
            GatewayProfileRow.schema_version == "2",
        )
        .order_by(GatewayProfileRow.name)
        .all()
    )
    return [_to_output(db, workspace_id, r) for r in rows]


@router.get(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}",
    response_model=ProfileOut,
)
def get_profile(
    workspace_id: str,
    profile_id: UUID,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    return _to_output(db, workspace_id, _load_profile(db, workspace_id, profile_id))


@router.put(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}",
    response_model=ProfileOut,
)
def update_working_copy(
    workspace_id: str,
    profile_id: UUID,
    body: UpdateWorkingCopyBody,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Overwrite the working copy. Save never touches live traffic.

    Refused once ``active_revision_id`` is set (profile is published) —
    the working_copy is locked in that state. To change a published
    profile, duplicate it into a fresh draft and edit that.

    Schema validation runs here so the UI catches typos immediately.
    Capability catalog is deferred to publish because presets change
    between LiteLLM version bumps and admins should be able to save an
    in-progress draft mid-migration.
    """
    profile = _load_profile(db, workspace_id, profile_id)
    if profile.active_revision_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Published profile — working_copy is locked. Duplicate "
                "this profile into a new draft to make changes."
            ),
        )
    parsed = _validate_working_copy(body.working_copy, check_capabilities=False)
    profile.working_copy = body.working_copy
    profile.model_alias = parsed.model_alias
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


@router.get("/{workspace_id}/gateway-profiles-v2/{profile_id}/rate-limits", response_model=ProfileRateLimitsOut)
def get_profile_rate_limits(
    workspace_id: str, profile_id: UUID,
    db: Session = Depends(get_db), _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
):
    _load_profile(db, workspace_id, profile_id)
    return _profile_rate_limits_output(db, workspace_id, profile_id)


@router.put("/{workspace_id}/gateway-profiles-v2/{profile_id}/rate-limits", response_model=ProfileRateLimitsOut)
def update_profile_rate_limits(
    workspace_id: str, profile_id: UUID, body: ProfileRateLimitsBody,
    db: Session = Depends(get_db), _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
):
    from app.core.workspace_context import set_workspace_rls

    set_workspace_rls(db, workspace_id)
    # Limits remain mutable even when the routing working copy is locked.
    _load_profile(db, workspace_id, profile_id, for_update=True)
    if body.agent_limits:
        raise HTTPException(400, "Set agent-wide limits under Agent IDs > Rate limits.")
    if not {"rpm", "tpm"} & body.model_fields_set:
        return _profile_rate_limits_output(db, workspace_id, profile_id)
    row = db.query(GatewayProfileRateLimit).filter(
        GatewayProfileRateLimit.workspace_id == workspace_id,
        GatewayProfileRateLimit.profile_id == profile_id,
        GatewayProfileRateLimit.agent_identity_id.is_(None),
    ).first()
    if row is None:
        row = GatewayProfileRateLimit(workspace_id=workspace_id, profile_id=profile_id)
        db.add(row)
    row.rpm, row.tpm = body.rpm, body.tpm
    db.commit()
    _log.info("gateway.profile_rate_limits.updated", workspace_id=workspace_id, profile_id=str(profile_id))
    return _profile_rate_limits_output(db, workspace_id, profile_id)


@router.delete(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}",
    status_code=204,
)
def delete_profile(
    workspace_id: str,
    profile_id: UUID,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Delete a *draft* only. A profile that has ever been published is
    refused — deleting it would cascade-drop its immutable revision
    history via the FK ``ON DELETE CASCADE``, contradicting the
    "revisions are forever" contract. Duplicate the profile if the
    admin wants a fresh working_copy; contact ops to archive if the
    published one truly needs to be retired."""
    profile = _load_profile(db, workspace_id, profile_id)

    if profile.active_revision_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Profile is published; deleting it would cascade-drop "
                "its revision history. Duplicate it if you want a fresh "
                "draft, or contact ops to archive."
            ),
        )
    revision_count = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile.id)
        .count()
    )
    if revision_count > 0:
        # active_revision_id is null but there are past revisions —
        # shouldn't happen under the current model (rollback keeps it
        # set), but belt-and-braces: revision history is sacred.
        raise HTTPException(
            status_code=409,
            detail=(
                "Profile has published revision history and can't be deleted."
            ),
        )
    db.delete(profile)
    db.commit()
