"""Helpers for the Gateway Profile v2 router (split from gateway_profiles_v2.py).

Cross-workspace path binding, publish-time credential checks, working-copy
validation, cond-code minting, import credential stripping, and the
smoke-test token / content helpers.
"""
from __future__ import annotations
from typing import Any
from uuid import UUID
import json
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id
from app.models.gateway_profile import (
    GatewayProfile as GatewayProfileRow,
    GatewayProfileRevision,
    GatewayProfileRateLimit,
)
from app.modules.guard.capability_catalog import (
    CapabilityMismatch,
    validate_targets_against_accepts,
)
from app.modules.guard.gateway_config import GatewayProfileV2
from app.routers.gateway_profiles_v2_schemas import (
    ImportGap,
    ProfileOut,
    ProfileRateLimitsOut,
    RevisionOut,
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


#: Publish-time key-presence contract per two-key integration.
#: (integration → (primary_key_names, vendor_key_names)). Kept next to
#: the publish check so the contract lives with the code that enforces
#: it — reviewer finding 4 called out that runtime knew the shape but
#: publish only checked row existence.
_TWO_KEY_INTEGRATION_CONTRACT: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "helicone_openai": (
        ("HELICONE_API_KEY",),
        ("OPENAI_API_KEY", "openai_api_key", "api_key"),
    ),
    "helicone_anthropic": (
        ("HELICONE_API_KEY",),
        ("ANTHROPIC_API_KEY", "anthropic_api_key", "api_key"),
    ),
}


def _verify_credentials_exist(
    db: Session, workspace_id: str, profile: "GatewayProfileV2",
) -> None:
    """Publish-time check that every target's ``credential_ref`` points at
    a Vault entry the workspace actually owns. Publishing to a missing
    credential would 500 at request time; catch it here so the admin sees
    the failure while the profile is still a draft.

    PR 5 review — two-key integrations (Helicone) additionally require
    BOTH the observability key + the upstream vendor key inside the
    same vault entry. Row existence alone is not enough because a stub
    row with just a placeholder would 500 at request time when the
    vendor resolver returns empty.
    """
    from app.core.credentials import get_vault_credential
    from app.models.environment import Environment
    from app.models.integration import Integration
    from app.modules.guard.gateway_config import (
        HTTPPassthroughTarget as _HTTPPassthroughTarget,
        parse_credential_ref,
    )

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

        # Two-key contract enforcement (Helicone).
        if isinstance(target, _HTTPPassthroughTarget):
            contract = _TWO_KEY_INTEGRATION_CONTRACT.get(target.integration)
            if contract is not None:
                primary_names, vendor_names = contract
                blob = get_vault_credential(db, workspace_id, str(env_id), name)
                if not any(blob.get(k) for k in primary_names):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"target {target.id!r} on {target.integration!r} "
                            f"needs one of {list(primary_names)!r} in vault "
                            f"entry {name!r}. Add the observability key and "
                            f"republish."
                        ),
                    )
                if not any(blob.get(k) for k in vendor_names):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"target {target.id!r} on {target.integration!r} "
                            f"needs one of {list(vendor_names)!r} in vault "
                            f"entry {name!r} (upstream vendor key). Add the "
                            f"vendor key alongside the observability key and "
                            f"republish."
                        ),
                    )


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


def _validate_working_copy(
    working_copy: dict[str, Any], *, check_capabilities: bool = True,
) -> GatewayProfileV2:
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
                # Historical shape: ("targets", i, "LiteLLMSDKTarget", ...).
                # PR 6/7 review — model_validator errors wrap the variant
                # name inside a ``function-after[...HTTPPassthroughTarget]``
                # synthetic segment. Detect exact match OR substring so
                # the filter still catches the noise.
                if len(loc_parts) >= 3 and isinstance(loc_parts[2], str):
                    seg = loc_parts[2]
                    for name in _TRANSPORT_VARIANT_NAME.values():
                        if name == seg or name in seg:
                            variant_name = name
                            break

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

    if not check_capabilities:
        return parsed

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


def _strip_credentials(working_copy: dict[str, Any]) -> tuple[dict[str, Any], list[ImportGap]]:
    """Return a copy of ``working_copy`` with every target's
    ``credential_ref`` set to empty, and the list of gaps the caller
    will need to fill.

    Never mutates the input. Empty ``credential_ref`` is what the
    editor's Save gate already blocks on (PR #2033), so the admin
    sees the exact same "pick a credential vault" banner they would
    for a duplicated profile or fresh preset.
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


def _profile_rate_limits_output(db: Session, workspace_id: str, profile_id: UUID) -> ProfileRateLimitsOut:
    from app.core.workspace_context import set_workspace_rls

    set_workspace_rls(db, workspace_id)
    rows = db.query(GatewayProfileRateLimit).filter(
        GatewayProfileRateLimit.workspace_id == workspace_id,
        GatewayProfileRateLimit.profile_id == profile_id,
        GatewayProfileRateLimit.agent_identity_id.is_(None),
    ).all()
    default = next((r for r in rows if r.agent_identity_id is None), None)
    return ProfileRateLimitsOut(
        rpm=default.rpm if default else None, tpm=default.tpm if default else None,
    )


def _mint_test_api_token(db: Session, workspace_id: str, creator_id: str):
    """Mint a short-lived ``cond_api_*`` machine token used only for the
    Test button. API-token flow (not session-token flow) because the
    gateway rejects session tokens that aren't linked to a
    guard_member_config row — API tokens fall back to the creator id
    via auth.resolve_agent_token, which is what we want here.

    Expires in one hour: the endpoint revokes on exit anyway; the TTL
    is a safety net if the revoke best-effort DELETE ever fails.
    """
    import secrets
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    from app.core.crypto import encrypt
    from app.modules.agent_identity.models import AgentIdentity
    from app.modules.agent_identity.router import API_TOKEN_PREFIX, _API_TOKEN_PREFIX_LEN

    plaintext = API_TOKEN_PREFIX + secrets.token_urlsafe(32)
    prefix = plaintext[:_API_TOKEN_PREFIX_LEN]
    now = datetime.now(timezone.utc)
    row = AgentIdentity(
        id=str(_uuid.uuid4()),
        workspace_id=workspace_id,
        name="test-gateway-token",
        provider="conduct",
        source="gateway_test_button",
        token_prefix=prefix,
        token_encrypted=encrypt({"token": plaintext}),
        token_type="api",
        token_name="test-gateway-token",
        created_by_clerk_user_id=creator_id,
        environment_id=None,
        created_at=now,
        last_used_at=None,
        expires_at=now + timedelta(hours=1),
    )
    db.add(row)
    return row, plaintext


def _extract_test_content(payload: Any) -> str | None:
    """Pull the assistant text from either an Anthropic or an OpenAI response."""
    if not isinstance(payload, dict):
        return None
    content = payload.get("content")
    if isinstance(content, list):
        parts = [
            part.get("text") for part in content
            if isinstance(part, dict)
            and part.get("type") in (None, "text")
            and isinstance(part.get("text"), str)
        ]
        joined = "\n".join(p for p in parts if p)
        if joined:
            return joined
    choices = payload.get("choices")
    if isinstance(choices, list) and choices:
        msg = choices[0].get("message") if isinstance(choices[0], dict) else None
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            return msg["content"]
    err = payload.get("error")
    if isinstance(err, dict) and isinstance(err.get("message"), str):
        return err["message"]
    return None
