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
    """Publish takes no arguments — it snapshots the working_copy and
    points ``active_revision_id`` at the new revision. Env selection is
    gone from the profile abstraction; vault refs live inside targets."""

    model_config = ConfigDict(extra="forbid")


class RollbackBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: UUID = Field(
        description=(
            "The historical revision to revert to. Must belong to the same "
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


class ProfileOut(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    model_alias: str | None
    cond_code: str
    active_revision_id: UUID | None
    working_copy: dict[str, Any] | None
    revisions: list[RevisionOut] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


# ─── Helpers ──────────────────────────────────────────────────────────


def _load_profile(
    db: Session, workspace_id: str, profile_id: UUID,
    *, for_update: bool = False,
) -> GatewayProfileRow:
    """Load a profile scoped to the caller's workspace.

    Set ``for_update=True`` for publish and rollback so a Postgres
    row-level lock (``SELECT ... FOR UPDATE``) serializes concurrent
    publishes on the same profile — otherwise two operators clicking
    Publish at once can race the version allocation loop AND the
    binding upsert. The lock is released when the request transaction
    commits or rolls back. On SQLite (unit tests) ``with_for_update()``
    is a no-op, so tests still work.
    """
    q = db.query(GatewayProfileRow).filter(
        GatewayProfileRow.id == profile_id,
        GatewayProfileRow.workspace_id == workspace_id,
    )
    if for_update:
        q = q.with_for_update()
    profile = q.one_or_none()
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


def _to_output(
    db: Session, workspace_id: str, profile: GatewayProfileRow,
) -> ProfileOut:
    revisions = (
        db.query(GatewayProfileRevision)
        .filter(GatewayProfileRevision.profile_id == profile.id)
        .order_by(GatewayProfileRevision.version.desc())
        .all()
    )
    return ProfileOut(
        id=profile.id,
        workspace_id=profile.workspace_id,
        name=profile.name,
        model_alias=profile.model_alias,
        cond_code=profile.cond_code,
        active_revision_id=profile.active_revision_id,
        working_copy=profile.working_copy,
        revisions=[
            RevisionOut(
                id=r.id, version=r.version,
                published_by=r.published_by, published_at=r.published_at,
            )
            for r in revisions
        ],
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


# ─── cond_code generation ──────────────────────────────────────────────

# Alphabet excludes visually ambiguous characters (0, O, 1, l, I) so
# codes printed in docs/URLs are unambiguous. Base 32 → ~5 bits/char, 8
# chars → 40 bits of entropy, effectively zero collision at scale.
_COND_CODE_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_COND_CODE_LENGTH = 8


def _generate_cond_code() -> str:
    import secrets
    return "".join(secrets.choice(_COND_CODE_ALPHABET) for _ in range(_COND_CODE_LENGTH))


def _generate_unique_cond_code(db: Session, workspace_id: str) -> str:
    """Generate a cond_code that doesn't collide within this workspace.

    Collision at 40 bits within a single workspace's dozen-or-so profiles
    is astronomically unlikely, but the uniqueness constraint is real so
    we retry the small chance we're wrong. Bounded retries (10) — hitting
    that many collisions means something is very wrong, and 500ing is
    the right response.
    """
    for _ in range(10):
        candidate = _generate_cond_code()
        exists = (
            db.query(GatewayProfileRow)
            .filter(
                GatewayProfileRow.workspace_id == workspace_id,
                GatewayProfileRow.cond_code == candidate,
            )
            .first()
        )
        if exists is None:
            return candidate
    raise HTTPException(
        status_code=500,
        detail="Could not generate a unique cond_code — retry the request.",
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


@router.post(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/publish",
    response_model=ProfileOut,
)
def publish_profile(
    workspace_id: str,
    profile_id: UUID,
    body: PublishBody,  # noqa: ARG001 — kept for future extensions (comment/message)
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    caller: str = Depends(require_permission("platform.credentials.manage")),
):
    """Atomic publish: freeze working_copy → new revision → activate.

    Reads ``working_copy``, validates against schema + capability
    catalog, verifies vault credentials in the payload actually exist,
    inserts a new revision, and points ``active_revision_id`` at it.
    Editing the working copy after publish is refused; the caller has
    to duplicate the profile to make further changes.

    Environment is not part of publish — vault refs inside the
    working_copy already scope credentials to an environment.
    """
    # Row-level lock: two operators publishing the same profile at the
    # same time would otherwise race the version-allocation loop.
    # FOR UPDATE serializes them; the second one sees the first one's
    # committed state before it starts.
    profile = _load_profile(db, workspace_id, profile_id, for_update=True)
    if not profile.working_copy:
        raise HTTPException(
            status_code=400,
            detail="working_copy is empty — nothing to publish",
        )
    if profile.active_revision_id is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Profile is already published. Duplicate to create a new "
                "draft; to revert to an earlier revision, use rollback."
            ),
        )

    # Pin the working-copy snapshot the instant we've validated it.
    # If a concurrent PUT lands mid-publish, we still write the version
    # the operator saw when they clicked Publish — never a mix of the
    # validated shape with an already-drifted body. Copy at the top
    # level so subsequent mutations to profile.working_copy don't
    # bleed into the pinned snapshot.
    working_snapshot: dict[str, Any] = dict(profile.working_copy)
    parsed = _validate_working_copy(working_snapshot)

    # Credential ownership check — every target's vault ref must
    # resolve to a credential in one of this workspace's environments.
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

    # Activate the new revision + cache the alias on the parent row so
    # the /list view is cheap.
    profile.active_revision_id = revision.id
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
    caller: str = Depends(require_permission("platform.credentials.manage")),  # noqa: ARG001 — kept in signature for RBAC enforcement
):
    """Point ``active_revision_id`` at a historical revision.

    Cross-profile revisions are rejected as a defense-in-depth check —
    the URL already scopes to a profile, but a mismatched revision id
    in the body could otherwise silently repoint one profile at
    another's snapshot.

    The working_copy is refreshed to match the rolled-back revision
    so the UI shows the shape that's actually being served. It stays
    locked (active_revision_id remains set) — to change the shape,
    duplicate the profile.
    """
    profile = _load_profile(db, workspace_id, profile_id, for_update=True)

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

    # Bring the working_copy back in sync with the revision the admin
    # rolled back to. Republish restores active_revision_id when they
    # tweak and re-publish; until then, editing is unlocked so the
    # rollback isn't a dead end.
    try:
        snapshot_parsed = GatewayProfileV2.model_validate(revision.snapshot)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"historical revision failed re-validation: {exc}",
        ) from exc

    profile.active_revision_id = revision.id
    profile.working_copy = dict(revision.snapshot)
    profile.model_alias = snapshot_parsed.model_alias
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
