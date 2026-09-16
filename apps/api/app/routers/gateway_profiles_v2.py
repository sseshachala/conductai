"""Gateway Profile v2 CRUD + publish + rollback (#2001, commit 3/4).

Prefix ``/workspaces/{workspace_id}/gateway-profiles-v2`` keeps the v2
endpoints strictly separate from the legacy ``/workspaces/{workspace_id}
/gateways`` router. Nothing here reads or writes v1 columns; a workspace
stays on v1 until an admin publishes at least one v2 profile.

Endpoint map:

    POST   /               create draft (working_copy only, no revision)
    GET    /               list profiles in this workspace
    GET    /{profile_id}   read one — working_copy + revisions + bindings
    PUT    /{profile_id}   update working_copy (schema-validated)
    DELETE /{profile_id}   drop draft (rejected if any binding points at it)
    POST   /{profile_id}/publish       atomic: revision + binding
    POST   /{profile_id}/rollback      atomic: binding → older revision
    GET    /{profile_id}/revisions     list history

Publish is the load-bearing operation:

1. Load ``working_copy`` from the profile row.
2. Parse against ``GatewayProfileV2`` (Pydantic schema).
3. Run ``validate_targets_against_accepts`` (capability catalog).
4. In one transaction:
   - Insert a new ``gateway_profile_revisions`` row with
     ``version = max(existing) + 1``.
   - Upsert the ``gateway_profile_bindings`` row for
     ``(workspace_id, environment_id, model_alias)`` to the new
     revision.
   - Cache ``profile.model_alias`` on the parent row for cheap listing.

Rollback is the same atomic pointer-swap without the revision insert;
history is intact and the previous binding is discoverable via the
``revisions`` list.

Everything Guard owns (permissions, spend, allowed destinations),
Gateway runtime owns (retry classification), or LiteLLM owns
(translation) is deliberately absent from this router. Governance
policy still runs regardless of which revision serves.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.gateway_profile import (
    GatewayProfile as GatewayProfileRow,
    GatewayProfileBinding,
    GatewayProfileBindingEvent,
    GatewayProfileRevision,
)
from app.modules.guard.capability_catalog import (
    CapabilityMismatch,
    validate_targets_against_accepts,
)
from app.modules.guard.gateway_config import GatewayProfileV2


router = APIRouter(
    prefix="/workspaces",
    tags=["gateway-profiles-v2"],
)


# ─── Cross-workspace defense ──────────────────────────────────────────


def _authorized_workspace_id(
    workspace_id: str,
    _ws: str = Depends(get_workspace_id),
) -> str:
    """Bind URL ``workspace_id`` to the caller's authenticated workspace.

    Without this dep, endpoints would authorize against the token but
    read/write resources for whatever workspace UUID appeared in the URL.
    An authorized caller in workspace A could then address workspace B's
    profiles by changing one path segment.

    Returns 404 (not 403) so the endpoint does not confirm the existence
    of resources belonging to another workspace.
    """
    if str(workspace_id) != str(_ws):
        raise HTTPException(status_code=404, detail="Profile not found")
    return workspace_id


def _verify_environment_belongs_to_workspace(
    db: Session, workspace_id: str, environment_id: UUID,
) -> None:
    """Publish/rollback bind to an environment UUID supplied in the body.
    Without this check, an admin in workspace A could bind a v2 profile
    to workspace B's environment id (the composite PK on
    ``gateway_profile_bindings`` would happily accept it — no FK from
    (environment_id) to (workspace_id, environment_id) exists at the DB
    level).
    """
    from app.models.environment import Environment
    env = (
        db.query(Environment)
        .filter(
            Environment.id == environment_id,
            Environment.workspace_id == workspace_id,
        )
        .one_or_none()
    )
    if env is None:
        raise HTTPException(
            status_code=404,
            detail="environment not found in this workspace",
        )


def _verify_credentials_exist(
    db: Session, workspace_id: str, profile: "GatewayProfileV2",
) -> None:
    """Publish-time check that every target's ``credential_ref`` points at
    a Vault entry the workspace actually owns. Publishing to a missing
    credential would 500 at request time; catch it here so the admin sees
    the failure while the profile is still a draft.
    """
    from app.models.environment import Environment
    from app.models.integration import Integration
    from app.modules.guard.gateway_config import parse_credential_ref

    for target in profile.targets:
        try:
            env_id, name = parse_credential_ref(target.credential_ref)
        except Exception as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"target {target.id!r} credential_ref malformed: {exc}"
                ),
            ) from exc
        # The environment must belong to this workspace.
        env = (
            db.query(Environment)
            .filter(
                Environment.id == env_id,
                Environment.workspace_id == workspace_id,
            )
            .one_or_none()
        )
        if env is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"target {target.id!r} credential_ref points at an "
                    f"environment not owned by this workspace"
                ),
            )
        # And a credential row with this handle must exist inside it.
        cred = (
            db.query(Integration)
            .filter(
                Integration.workspace_id == workspace_id,
                Integration.environment_id == env_id,
                Integration.handle == name,
            )
            .one_or_none()
        )
        if cred is None:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"target {target.id!r} credential_ref {target.credential_ref!r} "
                    f"has no matching Vault entry — create the credential "
                    f"in Settings → Vault before publishing"
                ),
            )


# ─── Request / response DTOs ──────────────────────────────────────────


class CreateProfileBody(BaseModel):
    """Minimum shape for creating a draft — name + initial working_copy."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    working_copy: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Initial GatewayProfileV2 shape. Empty dict = truly empty draft "
            "(admin will fill it via PUT before publishing)."
        ),
    )


class UpdateWorkingCopyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    working_copy: dict[str, Any] = Field(
        description="Full GatewayProfileV2 shape. Partial updates not supported."
    )


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: UUID = Field(
        description=(
            "Which environment to bind the new revision to. Publish is scoped "
            "per-environment; staging and prod are separate bindings."
        )
    )


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    environment_id: UUID
    revision_id: UUID = Field(
        description=(
            "The historical revision to bind to. Must belong to the same "
            "profile — cross-profile rollback is a security bug, not a feature."
        )
    )


class RevisionOut(BaseModel):
    id: UUID
    version: int
    published_by: str
    published_at: datetime
    # snapshot deliberately omitted from the list view — one revision can be
    # ~2KB of JSON and workspaces will accumulate many. Fetch via the
    # dedicated snapshot endpoint if the UI needs a diff.


class BindingOut(BaseModel):
    workspace_id: UUID
    environment_id: UUID
    model_alias: str
    revision_id: UUID
    updated_at: datetime


class ProfileOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    model_alias: str | None
    working_copy: dict[str, Any] | None
    revisions: list[RevisionOut] = Field(default_factory=list)
    bindings: list[BindingOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ─── Helpers ──────────────────────────────────────────────────────────


def _load_profile(
    db: Session, workspace_id: str, profile_id: UUID,
) -> GatewayProfileRow:
    profile = (
        db.query(GatewayProfileRow)
        .filter(
            GatewayProfileRow.id == profile_id,
            GatewayProfileRow.workspace_id == workspace_id,
        )
        .one_or_none()
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _current_bindings(
    db: Session, workspace_id: str, profile_id: UUID,
) -> list[GatewayProfileBinding]:
    """Return bindings that currently point at any revision of this profile.

    Runs two straightforward queries and joins in Python rather than a
    subquery / IN clause. Revisions-per-profile is small (single digits
    to low double digits over the profile's lifetime), and both indices
    already exist on the joining columns.
    """
    revisions = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile_id)
        .all()
    )
    if not revisions:
        return []
    revision_id_set = {r.id for r in revisions}
    bindings = (
        db.query(GatewayProfileBinding)
        .filter(GatewayProfileBinding.workspace_id == workspace_id)
        .all()
    )
    return [b for b in bindings if b.revision_id in revision_id_set]


def _to_output(
    db: Session, workspace_id: str, profile: GatewayProfileRow,
) -> ProfileOut:
    revisions = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile.id)
        .order_by(GatewayProfileRevision.version.desc())
        .all()
    )
    bindings = _current_bindings(db, workspace_id, profile.id)
    return ProfileOut(
        id=profile.id,
        workspace_id=profile.workspace_id,
        name=profile.name,
        model_alias=profile.model_alias,
        working_copy=profile.working_copy,
        revisions=[
            RevisionOut(
                id=r.id, version=r.version,
                published_by=r.published_by, published_at=r.published_at,
            )
            for r in revisions
        ],
        bindings=[
            BindingOut(
                workspace_id=b.workspace_id,
                environment_id=b.environment_id,
                model_alias=b.model_alias,
                revision_id=b.revision_id,
                updated_at=b.updated_at,
            )
            for b in bindings
        ],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


def _validate_working_copy(working_copy: dict[str, Any]) -> GatewayProfileV2:
    """Parse + capability-catalog check. Raises 400 on either failure."""
    try:
        parsed = GatewayProfileV2.model_validate(working_copy)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"schema invalid: {exc}",
        ) from exc
    try:
        validate_targets_against_accepts(
            accepts=parsed.accepts, targets=parsed.targets,
        )
    except CapabilityMismatch as exc:
        raise HTTPException(
            status_code=400, detail=f"capability check failed: {exc}",
        ) from exc
    return parsed


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
    """
    profile = GatewayProfileRow(
        workspace_id=workspace_id,
        environment_id=None,       # v2 uses bindings, not row env
        name=body.name,
        schema_version="2",
        config={},                  # v1 column intentionally empty for v2 rows
        working_copy=body.working_copy or None,
        model_alias=body.working_copy.get("model_alias") if body.working_copy else None,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


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

    Schema validation runs here so the UI catches typos immediately.
    Capability catalog is deferred to publish because presets change
    between LiteLLM version bumps and admins should be able to save an
    in-progress draft mid-migration.
    """
    profile = _load_profile(db, workspace_id, profile_id)
    try:
        parsed = GatewayProfileV2.model_validate(body.working_copy)
    except Exception as exc:
        raise HTTPException(
            status_code=400, detail=f"schema invalid: {exc}",
        ) from exc
    profile.working_copy = body.working_copy
    profile.model_alias = parsed.model_alias
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


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
    "revisions are forever" contract. Unbind, then archive out-of-band
    if the profile truly needs to be retired."""
    profile = _load_profile(db, workspace_id, profile_id)

    # Even one historical revision → refuse. This is stricter than the
    # earlier "any active binding" check because a rolled-back profile
    # with no current binding still has publish history that other
    # bindings could roll back to.
    revision_count = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile.id)
        .count()
    )
    if revision_count > 0:
        raise HTTPException(
            status_code=409,
            detail=(
                "Profile has published revisions; deleting it would "
                "cascade-drop that history. Unbind and leave the profile "
                "in place, or contact ops to archive it."
            ),
        )
    db.delete(profile)
    db.commit()


@router.post(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/publish",
    response_model=ProfileOut,
)
def publish_profile(
    workspace_id: str,
    profile_id: UUID,
    body: PublishBody,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    caller: str = Depends(require_permission("platform.credentials.manage")),
):
    """Atomic publish: new revision + binding pointer swap.

    Reads ``working_copy``, validates against schema + capability
    catalog, appends a new revision, and updates the binding for
    ``(workspace_id, environment_id, working_copy.model_alias)`` in one
    transaction. Editing the working copy after publish does not affect
    the served revision.
    """
    profile = _load_profile(db, workspace_id, profile_id)
    if not profile.working_copy:
        raise HTTPException(
            status_code=400,
            detail="working_copy is empty — nothing to publish",
        )

    # Pin the working-copy snapshot the instant we've validated it.
    # If a concurrent PUT lands mid-publish, we still write the version
    # the operator saw when they clicked Publish — never a mix of the
    # validated shape with an already-drifted body. Copy at the top
    # level so subsequent mutations to profile.working_copy don't
    # bleed into the pinned snapshot.
    working_snapshot: dict[str, Any] = dict(profile.working_copy)
    parsed = _validate_working_copy(working_snapshot)

    # Publish-time ownership checks — must happen BEFORE we mutate any
    # rows. Either failing here leaves the working copy intact.
    _verify_environment_belongs_to_workspace(
        db, workspace_id, body.environment_id,
    )
    _verify_credentials_exist(db, workspace_id, parsed)

    # Version allocation with unique-constraint retry. Concurrent
    # publish calls can otherwise race the max(version)+1 read and
    # both end up computing the same next version; the DB-level
    # uq_gateway_profile_revisions_profile_version constraint
    # catches the collision, we roll back, and retry with a fresh max.
    from sqlalchemy.exc import IntegrityError as _IntegrityError

    revision = None
    for _attempt in range(5):
        current_max = (
            db.query(func.max(GatewayProfileRevision.version))
            .filter(GatewayProfileRevision.profile_id == profile_id)
            .scalar()
            or 0
        )
        candidate = GatewayProfileRevision(
            profile_id=profile_id,
            version=current_max + 1,
            # Pinned snapshot — never re-read profile.working_copy
            # mid-loop, which could pick up a concurrent PUT and race
            # the validated shape.
            snapshot=working_snapshot,
            published_by=caller,
        )
        db.add(candidate)
        try:
            db.flush()  # forces the version uniqueness check
        except _IntegrityError:
            db.rollback()
            continue
        revision = candidate
        break
    if revision is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "concurrent publish contention — retry the request. If "
                "this persists, another admin is publishing this profile "
                "at the same time."
            ),
        )

    # Upsert the binding — one row per (workspace, env, alias).
    existing = (
        db.query(GatewayProfileBinding)
        .filter(
            GatewayProfileBinding.workspace_id == workspace_id,
            GatewayProfileBinding.environment_id == body.environment_id,
            GatewayProfileBinding.model_alias == parsed.model_alias,
        )
        .one_or_none()
    )
    prior_revision_id = existing.revision_id if existing else None
    if existing:
        existing.revision_id = revision.id
    else:
        db.add(GatewayProfileBinding(
            workspace_id=workspace_id,
            environment_id=body.environment_id,
            model_alias=parsed.model_alias,
            revision_id=revision.id,
        ))

    # Append-only audit — one row per binding change so history survives
    # subsequent rollbacks that would overwrite the current binding row.
    db.add(GatewayProfileBindingEvent(
        workspace_id=workspace_id,
        environment_id=body.environment_id,
        model_alias=parsed.model_alias,
        prior_revision_id=prior_revision_id,
        new_revision_id=revision.id,
        actor=caller,
        action="publish",
    ))

    # Cache the alias on the parent row so the /list view is cheap.
    profile.model_alias = parsed.model_alias
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


@router.post(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/rollback",
    response_model=ProfileOut,
)
def rollback_profile(
    workspace_id: str,
    profile_id: UUID,
    body: RollbackBody,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    caller: str = Depends(require_permission("platform.credentials.manage")),
):
    """Point a binding at a historical revision of this profile.

    Cross-profile revisions are rejected as a defense-in-depth check —
    the URL already scopes to a profile, but a mismatched revision id
    in the body could otherwise silently repoint one profile's binding
    at another profile's snapshot.

    The environment must belong to the caller's workspace (checked
    below), and every rollback writes an append-only audit row to
    ``gateway_profile_binding_events``.
    """
    profile = _load_profile(db, workspace_id, profile_id)

    _verify_environment_belongs_to_workspace(
        db, workspace_id, body.environment_id,
    )

    revision = (
        db.query(GatewayProfileRevision)
        .filter(
            GatewayProfileRevision.id == body.revision_id,
            GatewayProfileRevision.profile_id == profile_id,
        )
        .one_or_none()
    )
    if revision is None:
        raise HTTPException(
            status_code=404,
            detail="revision not found for this profile",
        )

    # The snapshot carries the model_alias — use it as the binding key
    # so we can't accidentally repoint a binding for a different alias.
    try:
        snapshot_parsed = GatewayProfileV2.model_validate(revision.snapshot)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"historical revision failed re-validation: {exc}",
        ) from exc

    existing = (
        db.query(GatewayProfileBinding)
        .filter(
            GatewayProfileBinding.workspace_id == workspace_id,
            GatewayProfileBinding.environment_id == body.environment_id,
            GatewayProfileBinding.model_alias == snapshot_parsed.model_alias,
        )
        .one_or_none()
    )
    prior_revision_id = existing.revision_id if existing else None
    if existing:
        existing.revision_id = body.revision_id
    else:
        db.add(GatewayProfileBinding(
            workspace_id=workspace_id,
            environment_id=body.environment_id,
            model_alias=snapshot_parsed.model_alias,
            revision_id=body.revision_id,
        ))

    # Append-only audit — capture actor + prior/new revision so the
    # history survives further rollbacks that would overwrite the
    # current binding row.
    db.add(GatewayProfileBindingEvent(
        workspace_id=workspace_id,
        environment_id=body.environment_id,
        model_alias=snapshot_parsed.model_alias,
        prior_revision_id=prior_revision_id,
        new_revision_id=body.revision_id,
        actor=caller,
        action="rollback",
    ))
    db.commit()
    db.refresh(profile)
    return _to_output(db, workspace_id, profile)


@router.get(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/revisions",
    response_model=list[RevisionOut],
)
def list_revisions(
    workspace_id: str,
    profile_id: UUID,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Full version history — newest first."""
    _load_profile(db, workspace_id, profile_id)  # 404 guard
    revisions = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile_id)
        .order_by(GatewayProfileRevision.version.desc())
        .all()
    )
    return [
        RevisionOut(
            id=r.id, version=r.version,
            published_by=r.published_by, published_at=r.published_at,
        )
        for r in revisions
    ]


@router.get(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/revisions/{revision_id}",
    response_model=dict[str, Any],
)
def get_revision_snapshot(
    workspace_id: str,
    profile_id: UUID,
    revision_id: UUID,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Return the immutable snapshot for one revision — used by the UI to
    diff historical revisions against the working copy.

    Verifies the parent profile belongs to the caller's workspace BEFORE
    resolving the revision. Without this, an authorized caller in
    workspace A could supply another workspace's profile_id +
    revision_id in the URL and read the snapshot — the URL-workspace
    check happened but the FK-scope check did not.
    """
    # Load the profile scoped to the caller's workspace first — 404 if
    # it belongs to anyone else. Same shape as _load_profile so the
    # error path is consistent across endpoints.
    _load_profile(db, workspace_id, profile_id)

    revision = (
        db.query(GatewayProfileRevision)
        .filter(
            GatewayProfileRevision.id == revision_id,
            GatewayProfileRevision.profile_id == profile_id,
        )
        .one_or_none()
    )
    if revision is None:
        raise HTTPException(status_code=404, detail="revision not found")
    return revision.snapshot
