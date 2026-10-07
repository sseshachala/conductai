"""Gateway Profile v2 CRUD + publish + rollback (#2001, commit 3/4).

Prefix ``/workspaces/{workspace_id}/gateway-profiles-v2`` keeps the v2
endpoints strictly separate from the legacy ``/workspaces/{workspace_id}
/gateways`` router. Nothing here reads or writes v1 columns; a workspace
stays on v1 until an admin publishes at least one v2 profile.

Endpoint map:

    POST   /               create draft (working_copy only, no revision)
    GET    /               list profiles in this workspace
    GET    /{profile_id}   read one — working_copy + revisions + active_revision
    PUT    /{profile_id}   update working_copy (schema-validated)
    DELETE /{profile_id}   drop draft
    POST   /{profile_id}/publish       atomic: revision + active_revision_id swap
    POST   /{profile_id}/rollback      atomic: active_revision_id → older revision
    GET    /{profile_id}/revisions     list history

Publish is the load-bearing operation:

1. Load ``working_copy`` from the profile row.
2. Parse against ``GatewayProfileV2`` (Pydantic schema).
3. Run ``validate_targets_against_accepts`` (capability catalog).
4. In one transaction:
   - Insert a new ``gateway_profile_revisions`` row with
     ``version = max(existing) + 1``.
   - Swap ``gateway_profiles.active_revision_id`` to the new revision.
   - Cache ``profile.model_alias`` on the parent row for cheap listing.

Rollback is the same atomic pointer-swap without the revision insert;
history is intact and the previous ``active_revision_id`` is discoverable
via the ``revisions`` list.

**v3 schema note**: bindings by ``(workspace_id, environment_id, model_alias)``
are gone. v3 resolves by ``cond_code`` (parsed from the client's
``model:`` field) directly against ``gateway_profiles.active_revision_id``
— environment is carried inside each target's ``credential_ref``. Any
reference to a "bindings" table in older comments/tests is stale.

Everything Guard owns (permissions, spend, allowed destinations),
Gateway runtime owns (retry classification), or LiteLLM owns
(translation) is deliberately absent from this router. Governance
policy still runs regardless of which revision serves.
"""
from __future__ import annotations

from typing import Any, Literal
from uuid import UUID


import httpx
import structlog
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.gateway_profile import (
    GatewayProfileRevision,
)
from app.modules.guard.gateway_config import GatewayProfileV2
from app.routers.gateway_profiles_v2_schemas import (
    ProfileOut,
    PublishBody,
    RevisionOut,
    RollbackBody,
)
from app.routers.gateway_profiles_v2_helpers import (
    _authorized_workspace_id,
    _extract_test_content,
    _load_profile,
    _mint_test_api_token,
    _to_output,
    _validate_working_copy,
    _verify_credentials_exist,
)
from app.routers.gateway_profiles_v2_crud import router

# Re-exported for callers that import these names from this module.
from app.routers.gateway_profiles_v2_schemas import (  # noqa: E402,F401
    CreateProfileBody,
    ImportProfileBody,
    ProfileRateLimitsBody,
    UpdateWorkingCopyBody,
)
from app.routers.gateway_profiles_v2_helpers import (  # noqa: E402,F401
    _strip_credentials,
)
from app.routers.gateway_profiles_v2_crud import (  # noqa: E402,F401
    create_profile,
    get_profile,
    get_profile_rate_limits,
    list_profiles,
    update_profile_rate_limits,
    update_working_copy,
)

_log = structlog.get_logger(__name__)


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


# ─── Smoke test (#2026) ────────────────────────────────────────────────

class TestProfileIn(BaseModel):
    prompt: str = Field(min_length=1, max_length=4000)
    provider: Literal["anthropic", "openai"]


class TestProfileOut(BaseModel):
    ok: bool
    status: int
    content: str | None
    body: str


@router.post(
    "/{workspace_id}/gateway-profiles-v2/{profile_id}/test",
    response_model=TestProfileOut,
)
def test_profile(
    workspace_id: str,
    profile_id: UUID,
    body: TestProfileIn,
    db: Session = Depends(get_db),
    _ws: str = Depends(_authorized_workspace_id),
    creator_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
) -> TestProfileOut:
    """Mint a short-lived ``test-gateway-token``, hit the gateway server-side,
    revoke, return the response. Dashboard host can't call the gateway
    origin from the browser (CORS not open for browsers by design), so
    the round trip is proxied through here.

    Only published profiles are testable — a draft has no active revision
    to resolve against.
    """
    profile = _load_profile(db, workspace_id, profile_id)
    if profile.active_revision_id is None:
        raise HTTPException(status_code=409, detail="Profile is not published yet")

    alias = profile.model_alias or ""
    model = f"cond-{profile.cond_code}-{alias}" if alias else f"cond-{profile.cond_code}"

    identity, plaintext = _mint_test_api_token(db, workspace_id, creator_id)
    db.commit()

    try:
        base = settings.conduct_proxy_url.rstrip("/")
        if body.provider == "anthropic":
            url = f"{base}/anthropic/v1/messages"
            payload: dict[str, Any] = {
                "model": model,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": body.prompt}],
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {plaintext}",
                "anthropic-version": "2023-06-01",
            }
        else:  # openai
            # Gateway serves the OpenAI surface at /openai/v1/... (gateway_proxy.py).
            url = f"{base}/openai/v1/chat/completions"
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": body.prompt}],
                "stream": False,
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {plaintext}",
            }

        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as err:
            return TestProfileOut(
                ok=False, status=0, content=None,
                body=f"Gateway request failed: {err}",
            )

        text = resp.text
        parsed_content: str | None = None
        ctype = resp.headers.get("content-type", "")
        if ctype.startswith("application/json"):
            try:
                parsed = resp.json()
                parsed_content = _extract_test_content(parsed)
            except ValueError:
                parsed_content = None

        return TestProfileOut(
            ok=resp.status_code < 400,
            status=resp.status_code,
            content=parsed_content,
            body=text,
        )
    finally:
        # Expire (not delete) so the audit rows this call just wrote keep
        # their agent_identity_id FK intact — guard_audit_events uses
        # ON DELETE SET NULL, so a hard delete would blank the identity
        # column on the row the user is about to look at. Setting
        # expires_at to now still invalidates the token immediately
        # (see auth.resolve_agent_identity_row: ai_row.expires_at < now
        # returns None).
        try:
            from datetime import datetime as _dt, timezone as _tz
            identity.expires_at = _dt.now(_tz.utc)
            db.add(identity)
            db.commit()
        except Exception as err:  # noqa: BLE001
            _log.warning(
                "gateway.test.expire_failed",
                identity_id=identity.id,
                workspace_id=workspace_id,
                error=str(err),
            )
