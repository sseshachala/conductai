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

from datetime import datetime
from typing import Any
from uuid import UUID

import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
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


class ImportProfileBody(BaseModel):
    """Import a profile from a portable JSON payload.

    ``working_copy`` is the same shape the editor's Save posts, i.e. a
    ``GatewayProfileV2`` dict. The server ALWAYS strips
    ``credential_ref`` from every target on import (defense against
    accidentally-committed vault refs in checked-in JSON, and to keep
    exports portable across workspaces + environments).

    ``name_override`` lets the caller land the imported profile under
    a different name than what's in the JSON's ``name`` field — useful
    when the source profile's name is already taken in the target
    workspace. When absent, the JSON's ``name`` wins (or falls back
    to ``imported-profile`` if the JSON has no name).
    """
    model_config = ConfigDict(extra="forbid")

    working_copy: dict[str, Any] = Field(
        description="Portable GatewayProfileV2 shape. credential_ref values are stripped on import."
    )
    name_override: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Optional profile name for the imported draft (else use working_copy.name).",
    )


class ImportGap(BaseModel):
    """One target that needs credentials filled before publish."""
    target_index: int
    target_id: str
    transport: str
    reason: str


class ImportProfileOut(BaseModel):
    """Result of an import — created profile + gaps + a link the
    caller can open to finish setup."""
    profile: "ProfileOut"
    credential_gaps: list[ImportGap]
    next_url: str = Field(
        description="Absolute URL to the editor page for the created profile."
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


# Resolve the forward reference on ``ImportProfileOut.profile`` (which
# is typed as ``"ProfileOut"`` because ``ProfileOut`` is defined below
# ``ImportProfileOut``).
ImportProfileOut.model_rebuild()


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
    """Parse + capability-catalog check. Raises 400 on either failure.

    Errors are returned as a structured body so the UI can highlight the
    offending field on the specific target rather than showing a bare
    error string. Shape:

    ``{"detail": "...", "errors": [{"path": "targets.2.credential_ref",
      "message": "...", "target_index": 2}]}``

    The server is authoritative — the client-side capability catalog
    mirror at ``apps/web/src/lib/gatewayCapabilityCatalog.ts`` is a UX
    hint, not a gate. This function's decision is what publishes stand
    or fall on.
    """
    from pydantic import ValidationError

    # Map the transport literal on each target back to the discriminated-
    # union variant class name Pydantic uses in loc paths. Absence in
    # this map means an unknown transport (Pydantic will already have
    # emitted a top-level literal_error we surface verbatim).
    _TRANSPORT_VARIANT_NAME: dict[str, str] = {
        "native_http": "NativeHTTPTarget",
        "litellm_sdk": "LiteLLMSDKTarget",
        "http_passthrough": "HTTPPassthroughTarget",
    }

    try:
        parsed = GatewayProfileV2.model_validate(working_copy)
    except ValidationError as exc:
        raw_targets = working_copy.get("targets")
        raw_targets_list = raw_targets if isinstance(raw_targets, list) else []

        errors: list[dict[str, Any]] = []
        for e in exc.errors():
            loc_parts = e.get("loc", ())
            loc = ".".join(str(p) for p in loc_parts)
            # ``loc`` for a targets-list error looks like
            # ("targets", 2, "credential_ref") for direct field errors
            # or ("targets", 2, "LiteLLMSDKTarget", "credential_ref")
            # when the discriminated union tried each variant. Extract
            # the target index so the UI can highlight the row, and
            # collect the variant name (if any) so we can filter noise
            # from mismatched-variant errors below.
            target_index: int | None = None
            variant_name: str | None = None
            if (
                len(loc_parts) >= 2
                and loc_parts[0] == "targets"
                and isinstance(loc_parts[1], int)
            ):
                target_index = loc_parts[1]
                if len(loc_parts) >= 3 and isinstance(loc_parts[2], str) \
                        and loc_parts[2] in _TRANSPORT_VARIANT_NAME.values():
                    variant_name = loc_parts[2]

            # Discriminated-union noise filter (self-review #2): when
            # a target's ``transport`` is set, Pydantic still walks the
            # other two variants and emits per-variant errors that are
            # confusing ("target[0].NativeHTTPTarget.transport should
            # be native_http" when the user chose litellm_sdk). Drop
            # those; keep only errors whose variant matches the
            # target's declared transport.
            if variant_name is not None and target_index is not None:
                if 0 <= target_index < len(raw_targets_list):
                    declared_transport = raw_targets_list[target_index].get("transport") \
                        if isinstance(raw_targets_list[target_index], dict) else None
                    expected_variant = _TRANSPORT_VARIANT_NAME.get(
                        declared_transport or ""
                    )
                    if expected_variant and variant_name != expected_variant:
                        continue  # skip mismatched-variant noise
                    # Strip the variant name from the reported path so the
                    # UI sees ``targets.2.credential_ref`` regardless of
                    # which union variant matched.
                    loc = ".".join(
                        str(p) for i, p in enumerate(loc_parts) if i != 2
                    )

            errors.append({
                "path": loc,
                "message": e.get("msg", "invalid"),
                "target_index": target_index,
                "type": e.get("type", "value_error"),
            })

        # If the noise filter left us with zero errors (edge case: all
        # errors were mismatched-variant noise, which should never
        # happen if the input passed the top-level schema shape), fall
        # back to reporting the raw errors so nothing gets swallowed.
        if not errors:
            for e in exc.errors():
                loc_parts = e.get("loc", ())
                errors.append({
                    "path": ".".join(str(p) for p in loc_parts),
                    "message": e.get("msg", "invalid"),
                    "target_index": (
                        loc_parts[1]
                        if len(loc_parts) >= 2 and loc_parts[0] == "targets"
                        and isinstance(loc_parts[1], int) else None
                    ),
                    "type": e.get("type", "value_error"),
                })

        raise HTTPException(
            status_code=400,
            detail={"summary": "schema invalid", "errors": errors},
        ) from exc

    try:
        validate_targets_against_accepts(
            accepts=parsed.accepts, targets=parsed.targets,
        )
    except CapabilityMismatch as exc:
        # CapabilityMismatch's message already names the target id +
        # missing operation + transport/integration. Preserve that in
        # the same structured shape so the UI has a consistent
        # ``detail`` object to render.
        raise HTTPException(
            status_code=400,
            detail={
                "summary": "capability check failed",
                "errors": [{
                    "path": "targets",
                    "message": str(exc),
                    "target_index": None,
                    "type": "capability_mismatch",
                }],
            },
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


# Keys we treat as secret-shaped anywhere in a target (top-level or
# nested in ``provider_options`` / ``headers`` / etc.). Matched
# case-insensitively. When we find one on import we reject the whole
# payload — the point of round-tripping via JSON is that credentials
# live in Vault, never in the file — so an inline secret is either
# leaked material or an admin mistake, both worth failing loudly.
# On export we recursively drop them from ``provider_options`` before
# returning so the exported JSON is safe to commit to a repo.
_SECRET_KEYS: frozenset[str] = frozenset({
    "api_key", "apikey", "api-key",
    "api_token", "apitoken", "api-token",
    "secret", "secret_key", "secret-key",
    "password", "passwd", "pwd",
    "token", "bearer_token", "auth_token",
    "authorization", "bearer",
    "private_key", "priv_key", "privkey",
})


def _is_secret_key(key: Any) -> bool:
    return isinstance(key, str) and key.strip().lower() in _SECRET_KEYS


def _find_inline_secret_key(node: Any, path: str) -> tuple[str, str] | None:
    """DFS scan for the first secret-shaped key with a truthy value.
    Returns ``(path, offending_key)`` or ``None``.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if _is_secret_key(k) and v not in (None, "", 0, False):
                return (f"{path}.{k}" if path else str(k), str(k))
            child_path = f"{path}.{k}" if path else str(k)
            hit = _find_inline_secret_key(v, child_path)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for i, v in enumerate(node):
            hit = _find_inline_secret_key(v, f"{path}[{i}]")
            if hit is not None:
                return hit
    return None


def _sanitise_secret_keys(node: Any) -> Any:
    """Recursively drop secret-shaped keys from ``node`` (mutates in
    place for dicts/lists, returns the node for chaining). Used on
    export so ``provider_options`` never leaks an inline api_key that
    somehow snuck past the create/update Save gate.
    """
    if isinstance(node, dict):
        for k in list(node.keys()):
            if _is_secret_key(k):
                del node[k]
            else:
                _sanitise_secret_keys(node[k])
    elif isinstance(node, list):
        for item in node:
            _sanitise_secret_keys(item)
    return node


def _validate_import_shape(working_copy: Any) -> None:
    """Reject payloads the editor can't render.

    The editor assumes ``working_copy`` is a dict and, if present,
    ``targets`` is a list of dicts. Anything else (dict, null, list of
    scalars) either crashes the editor or silently drops data; better
    to fail fast at the import boundary with a structured error the CLI
    + UI both format nicely.
    """
    if not isinstance(working_copy, dict):
        raise HTTPException(
            status_code=422,
            detail={
                "summary": "import payload must be an object",
                "errors": [{
                    "path": "$",
                    "message": (
                        "Top-level working_copy must be a JSON object. "
                        "Got: " + type(working_copy).__name__
                    ),
                    "target_index": None,
                    "type": "shape",
                }],
            },
        )
    targets = working_copy.get("targets")
    if targets is None:
        return
    if not isinstance(targets, list):
        raise HTTPException(
            status_code=422,
            detail={
                "summary": "targets must be a list",
                "errors": [{
                    "path": "targets",
                    "message": (
                        "``targets`` must be a JSON array. Got: "
                        + type(targets).__name__
                    ),
                    "target_index": None,
                    "type": "shape",
                }],
            },
        )
    for i, target in enumerate(targets):
        if not isinstance(target, dict):
            raise HTTPException(
                status_code=422,
                detail={
                    "summary": "target entries must be objects",
                    "errors": [{
                        "path": f"targets[{i}]",
                        "message": (
                            "Every target must be a JSON object. Got: "
                            + type(target).__name__
                        ),
                        "target_index": i,
                        "type": "shape",
                    }],
                },
            )


def _reject_inline_secrets(working_copy: dict[str, Any]) -> None:
    """Fail fast if the caller pasted an inline api_key / password /
    token anywhere inside a target. Credentials belong in Vault; the
    exported JSON already scrubs them, so an inline secret on import is
    either leaked material or an admin mistake.
    """
    targets = working_copy.get("targets")
    if not isinstance(targets, list):
        return
    for i, target in enumerate(targets):
        if not isinstance(target, dict):
            continue
        hit = _find_inline_secret_key(target, "")
        if hit is None:
            continue
        path, key = hit
        raise HTTPException(
            status_code=422,
            detail={
                "summary": "inline credential detected",
                "errors": [{
                    "path": f"targets[{i}].{path}",
                    "message": (
                        f"Inline secret-shaped key {key!r} found at "
                        f"targets[{i}].{path}. Credentials must live "
                        f"in Vault — remove the inline value and set "
                        f"``credential_ref`` after import."
                    ),
                    "target_index": i,
                    "type": "inline_secret",
                }],
            },
        )


def _strip_credentials(working_copy: dict[str, Any]) -> tuple[dict[str, Any], list[ImportGap]]:
    """Return a copy of ``working_copy`` with every target's
    ``credential_ref`` set to empty, and the list of gaps the caller
    will need to fill.

    Never mutates the input. Empty ``credential_ref`` is what the
    editor's Save gate already blocks on (PR #2033), so the admin
    sees the exact same "pick a credential vault" banner they would
    for a duplicated profile or fresh preset.

    Also scrubs any secret-shaped key nested inside ``provider_options``
    (defensive belt-and-braces — the Save gate blocks these on write,
    but exports go through this same helper so we can't rely on that).
    """
    stripped = json.loads(json.dumps(working_copy))  # deep copy via JSON round-trip
    gaps: list[ImportGap] = []
    targets = stripped.get("targets") if isinstance(stripped, dict) else None
    if isinstance(targets, list):
        for i, target in enumerate(targets):
            if not isinstance(target, dict):
                continue
            # Record only when the source HAD a credential — signals
            # to the caller that this target needs a pick, distinct
            # from "target had no credential to strip" (which the
            # editor's Save gate flags anyway).
            had_credential = bool(target.get("credential_ref"))
            target["credential_ref"] = ""
            # R1b: recursively drop secret-shaped keys from the
            # target (provider_options, headers, nested dicts). Export
            # feeds this same helper, so anything sitting in a stored
            # profile gets sanitised on the way out.
            _sanitise_secret_keys(target)
            gaps.append(ImportGap(
                target_index=i,
                target_id=str(target.get("id") or f"target-{i + 1}"),
                transport=str(target.get("transport") or "unknown"),
                reason=(
                    "credential_ref stripped on import — pick a vault"
                    if had_credential
                    else "credential_ref missing — pick a vault"
                ),
            ))
    return stripped, gaps


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

    Two hard fail-fast checks run first:
      * R3 shape gate — ``working_copy`` must be an object, and any
        ``targets`` must be a list of objects. Prevents editor crashes
        from ``{"targets": {}}`` / ``[null]`` type payloads.
      * R1a inline-secret gate — any secret-shaped key inside a target
        (api_key / token / password / etc.) is rejected. Credentials
        belong in Vault.
    """
    _validate_import_shape(body.working_copy)
    _reject_inline_secrets(body.working_copy)
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
