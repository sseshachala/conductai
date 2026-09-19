"""Environment-variable editor endpoints — the write path Vault UIs use.

Split out of ``credentials.py`` in the #2054 Phase 1 round-trip fix.
This module owns the read/write/delete contract for the flat env-var
view exposed to the settings UI. It:

- Preserves credential identity across the list → edit → save round trip.
  The client echoes ``handle`` and ``field`` back; the writer uses them
  verbatim instead of re-parsing display names. New rows typed by env-var
  name still fall through the ``_ENV_VAR_MAP`` alias table.

- Serializes concurrent writes via ``integrations.revision``. Callers
  MUST send ``expected_revision`` when updating an existing handle;
  a mismatch returns 409 with the current revision so the client can
  reload before retrying.

- Never deletes a credential because the client omitted it from a save.
  Removal requires an explicit call to ``DELETE /env-vars/{env_id}/handles/{handle}``.

- Reference-checks delete: gateway_profiles (config + working_copy +
  active revision snapshot) and mcp_servers (encrypted_auth handle
  refs) are enumerated authoritatively; workflow YAML is scanned for
  ``credentials.<handle>`` substrings on a best-effort basis. Any hit
  → 409 unless the caller passes ``force=true`` (audited).

The canonical alias table ``_ENV_VAR_MAP`` stays here — one home for the
mapping other modules import from (see ``runtime/mcp_credentials.py``).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session

from app.core.auth import audit, get_workspace_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.core.integration_writer import conditional_delete, conditional_update
from app.models.integration import Integration
from app.routers.env_vars_references import reference_report as _reference_report

router = APIRouter(prefix="/credentials", tags=["credentials"])


# Standard env var name → (handle, field). Kept in one place — no other
# module owns a parallel mapping. ``runtime/mcp_credentials.py`` imports
# ``_ENV_VAR_MAP`` from here.
_ENV_VAR_MAP: dict[str, tuple[str, str]] = {
    # Git (unified handle — provider stored as a field within the credential)
    "GITHUB_TOKEN":       ("git",          "token"),   # canonical display name
    "GIT_TOKEN":          ("git",          "token"),   # alias
    "GITHUB_PAT":         ("git",          "token"),   # alias
    "GITLAB_TOKEN":       ("git",          "token"),   # alias
    "BITBUCKET_TOKEN":    ("git",          "token"),   # alias
    "GIT_PROVIDER":       ("git",          "provider"),
    # Collaboration
    "SLACK_BOT_TOKEN":      ("slack",        "token"),           # canonical
    "SLACK_TOKEN":          ("slack",        "token"),           # alias
    "SLACK_SIGNING_SECRET": ("slack",        "signing_secret"),
    "LINEAR_API_KEY":     ("linear",       "api_key"),
    # Cloud / infra
    "DIGITALOCEAN_TOKEN": ("digitalocean", "token"),
    "DO_TOKEN":           ("digitalocean", "token"),
    "VERCEL_TOKEN":       ("vercel",       "token"),
    "MODAL_TOKEN_ID":     ("modal",        "token_id"),
    "MODAL_TOKEN_SECRET": ("modal",        "token_secret"),
    # AI
    "ANTHROPIC_API_KEY":  ("anthropic",    "api_key"),
    "PERPLEXITY_API_KEY": ("perplexity",   "api_key"),
    # Email
    "RESEND_API_KEY":     ("email",        "resend_api_key"),
    "SENDGRID_API_KEY":   ("email",        "sendgrid_api_key"),
    "EMAIL_FROM_NAME":    ("email",        "from_name"),
    "EMAIL_FROM_EMAIL":   ("email",        "from_email"),
}
# Reverse: (handle, field) → canonical env var name (first occurrence wins).
_ENV_VAR_REVERSE: dict[tuple[str, str], str] = {}
for _k, _v in _ENV_VAR_MAP.items():
    if _v not in _ENV_VAR_REVERSE:
        _ENV_VAR_REVERSE[_v] = _k


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class EnvVarUpsert(BaseModel):
    """One item in a bulk env-vars save payload.

    - ``key`` is a display name only; never authoritative for storage identity.
    - ``handle`` + ``field`` together identify an existing row and MUST be
      passed together. Server uses them verbatim (case preserved, no
      re-parsing of ``key``). Absent → treated as a new user-typed row and
      falls through the ``_ENV_VAR_MAP`` alias table.
    - ``value`` MUST be a string. Empty string is a literal empty value.
      Removing a field or a row goes through the DELETE endpoint — PUT
      does not carry a clear semantic (avoids bypassing reference checks).
    - ``expected_revision`` MUST be passed when updating any existing row;
      the writer refuses to apply an update whose expected revision doesn't
      match the current row. All items targeting the same handle in one
      payload MUST agree on ``expected_revision``.
    """
    key: str
    value: str
    handle: str | None = None
    field: str | None = None
    expected_revision: int | None = None

    @model_validator(mode="after")
    def _identity_pair(self) -> "EnvVarUpsert":
        # Partial identity is ambiguous — reject it so a stale client can't
        # accidentally masquerade as a new-row create.
        if bool(self.handle) != bool(self.field):
            raise ValueError(
                "handle and field must both be provided together (existing row) "
                "or both omitted (new row)."
            )
        return self


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_env_ownership(db: Session, env_id: str, workspace_id: str) -> None:
    """Refuse cross-workspace writes to an environment."""
    from app.models.environment import Environment as _Env
    env = db.query(_Env).filter(
        _Env.id == env_id,
        _Env.workspace_id == workspace_id,
    ).first()
    if not env:
        # 404 not 403 — leaks nothing about whether the env exists in
        # another workspace.
        raise HTTPException(status_code=404, detail="Environment not found")


def _raise_stale_revision(db: Session, row_id, handle: str) -> None:
    """Refetch the row so the client can reload against a real revision."""
    current = db.query(Integration).filter(Integration.id == row_id).first()
    raise HTTPException(
        status_code=409,
        detail={
            "code": "stale_revision",
            "handle": handle,
            "current_revision": int(current.revision) if current else 0,
        },
    )


def _resolve_identity(item: EnvVarUpsert) -> tuple[str, str]:
    """Existing rows keep their identity; new rows fall through the alias map.

    Casing is preserved on the arbitrary-name fallback (``env_vars.<KEY>``)
    so uppercase user variables survive a round trip. Reserved-field casing
    fixes in other writers (identity provisioning, gateway push) are a
    separate follow-up in the same epic.
    """
    if item.handle and item.field:
        return item.handle, item.field
    mapped = _ENV_VAR_MAP.get(item.key)
    if mapped:
        return mapped
    return ("env_vars", item.key)


# ---------------------------------------------------------------------------
# GET — list env vars for an environment (unchanged behavior)
# ---------------------------------------------------------------------------


@router.get("/env-vars/{env_id}")
def list_env_vars(
    env_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Return all credentials for an environment as flat key-value pairs.

    Each row includes ``handle``, ``field``, and ``revision`` so the client
    can echo them back verbatim on save and use the revision for optimistic
    concurrency. See ``EnvVarUpsert`` for the write contract.
    """
    _verify_env_ownership(db, env_id, workspace_id)

    rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
    ).order_by(Integration.created_at).all()

    result = []
    for row in rows:
        if not row.encrypted_credentials:
            continue
        creds = decrypt(row.encrypted_credentials)
        for field, value in creds.items():
            if row.handle == "env_vars":
                # Arbitrary user-typed variable — display name is the field
                # name verbatim (casing preserved on write; see _resolve_identity).
                key = field
            else:
                key = _ENV_VAR_REVERSE.get((row.handle, field)) or f"{row.handle.upper()}_{field.upper()}"
            result.append({
                "key": key,
                "value": value,
                "handle": row.handle,
                "field": field,
                "revision": row.revision,
            })
    return result


# ---------------------------------------------------------------------------
# PUT — save (upsert-only; never deletes)
# ---------------------------------------------------------------------------


@router.put("/env-vars/{env_id}", status_code=200)
def save_env_vars(
    env_id: str,
    body: list[EnvVarUpsert],
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Upsert env vars for an environment. **Never deletes.**

    Contract:
    - Each item is grouped by ``(handle, field)`` identity. Duplicate
      targets in a single payload → 422.
    - Existing rows must be updated with the matching ``expected_revision``.
      Mismatch → 409 with the current revision so the client can reload.
    - Fields not present in the payload are preserved on the existing
      encrypted blob (multi-field credentials no longer lose columns on
      partial saves).
    - ``value=None`` clears the specific field. ``value=""`` sets it to
      the literal empty string. Row deletion requires the DELETE endpoint.
    - Handles omitted from the payload are **not** deleted.
    """
    _verify_env_ownership(db, env_id, workspace_id)

    # Reject duplicate targets across the payload — otherwise two items
    # would silently overwrite each other and last-write-wins would decide.
    seen_targets: set[tuple[str, str]] = set()
    resolved: list[tuple[tuple[str, str], EnvVarUpsert]] = []
    for item in body:
        handle, field = _resolve_identity(item)
        target = (handle, field)
        if target in seen_targets:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate target ({handle}, {field}) in payload.",
            )
        seen_targets.add(target)
        resolved.append((target, item))

    # Group by handle so we merge fields against existing storage once
    # per row, not once per payload item.
    grouped: dict[str, list[tuple[str, EnvVarUpsert]]] = {}
    for (handle, field), item in resolved:
        grouped.setdefault(handle, []).append((field, item))

    saved = 0
    for handle, items in grouped.items():
        existing = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == env_id,
            Integration.handle == handle,
        ).first()

        if existing:
            # Concurrency guard — every item on this handle MUST agree on the
            # same expected_revision. A mixed batch (rev=1 + rev=2 with actual=2)
            # would let a stale write ride the coattails of a current one.
            expected_revs = {i.expected_revision for _f, i in items}
            if None in expected_revs or len(expected_revs) != 1:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "expected_revision_inconsistent",
                        "handle": handle,
                        "current_revision": existing.revision,
                    },
                )
            expected_rev = next(iter(expected_revs))
            # Build the merged blob against the row we just read. Rejection
                # happens later via a conditional UPDATE so two racing writers
                # can't both pass this check and clobber each other.
            merged: dict[str, str] = {}
            if existing.encrypted_credentials:
                merged.update(decrypt(existing.encrypted_credentials))
            for field, item in items:
                merged[field] = item.value
            if not merged:
                # Should be unreachable now that clears go via DELETE, but
                # keep the guard so an empty result never claims success.
                raise HTTPException(
                    status_code=422,
                    detail=f"Save for handle '{handle}' produced an empty credential; use DELETE.",
                )
            new_ct = encrypt(merged)
            rowcount = conditional_update(
                db,
                existing.id,
                expected_revision=expected_rev,
                new_ciphertext=new_ct,
            )
            if rowcount == 0:
                _raise_stale_revision(db, existing.id, handle)
        else:
            # Brand-new row — expected_revision must NOT be sent; the row
            # didn't exist for the caller to have a revision for. If the
            # client sends one anyway we treat it as a stale reference.
            if any(i.expected_revision is not None for _f, i in items):
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "handle_missing",
                        "handle": handle,
                    },
                )
            new_fields = {field: item.value for field, item in items}
            row = Integration(
                workspace_id=workspace_id,
                environment_id=env_id,
                service=handle,
                handle=handle,
                auth_method="api_key",
                encrypted_credentials=encrypt(new_fields),
                revision=1,
            )
            db.add(row)
        saved += 1

    db.commit()
    return {"saved": saved}


# ---------------------------------------------------------------------------
# DELETE — explicit removal with reference checks
# ---------------------------------------------------------------------------


class DeleteEnvVarResponse(BaseModel):
    handle: str
    field: str | None
    deleted: bool
    references: dict[str, list[str]]


@router.delete("/env-vars/{env_id}/handles/{handle}")
def delete_env_var(
    env_id: str,
    handle: str,
    expected_revision: int,
    field: str | None = None,
    force: bool = False,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
):
    """Explicit deletion — either a single field or the whole handle row.

    Query params:
    - ``expected_revision`` (required) — must match ``integrations.revision``.
    - ``field`` (optional) — omit to delete the whole row; supply to clear
      only that field (row survives if other fields remain).
    - ``force`` (default false) — bypass the reference check.

    Reference checks:
    - Gateway profiles (config + working_copy + active revision snapshot)
      and MCP server encrypted_auth are enumerated authoritatively.
    - Workflow YAML is scanned best-effort for ``credentials.<handle>``
      substrings and returned under ``workflows_soft``.
    - Any non-empty list → 409 unless ``force=true``. Force deletions are
      recorded in the audit log with the reference report.
    """
    _verify_env_ownership(db, env_id, workspace_id)

    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == env_id,
        Integration.handle == handle,
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Credential not found")
    if row.revision != expected_revision:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "stale_revision",
                "handle": handle,
                "current_revision": row.revision,
            },
        )

    refs = _reference_report(db, workspace_id, env_id, handle)
    any_refs = any(refs.values())
    if any_refs and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "credential_referenced",
                "handle": handle,
                "references": refs,
            },
        )

    row_id = row.id
    if field is None:
        # Whole-row delete via conditional DELETE — rowcount 0 means a
        # concurrent writer beat us to the row.
        deleted = conditional_delete(db, row_id, expected_revision=expected_revision)
        if deleted == 0:
            _raise_stale_revision(db, row_id, handle)
        if any_refs:
            audit(
                db,
                workspace_id,
                "credential.force_delete",
                resource_type="integration",
                resource_id=str(row_id),
                metadata={
                    "handle": handle,
                    "environment_id": env_id,
                    "references": refs,
                },
            )
    else:
        # Field-only delete — merge, drop, re-encrypt via conditional UPDATE.
        # If dropping this field would leave the row empty, promote to a
        # whole-row delete so the caller can freely recreate the credential
        # afterwards. Reference protection already ran above; skipping it
        # here would be inconsistent between "field is the last one" and
        # "field is one of many".
        creds = decrypt(row.encrypted_credentials) if row.encrypted_credentials else {}
        if field not in creds:
            raise HTTPException(status_code=404, detail="Field not found on credential")
        del creds[field]
        if not creds:
            deleted = conditional_delete(db, row_id, expected_revision=expected_revision)
            if deleted == 0:
                _raise_stale_revision(db, row_id, handle)
            if any_refs:
                audit(
                    db,
                    workspace_id,
                    "credential.force_delete",
                    resource_type="integration",
                    resource_id=str(row_id),
                    metadata={
                        "handle": handle,
                        "environment_id": env_id,
                        "references": refs,
                        "reason": "last_field_removed",
                    },
                )
        else:
            new_ct = encrypt(creds)
            updated = conditional_update(
                db,
                row_id,
                expected_revision=expected_revision,
                new_ciphertext=new_ct,
            )
            if updated == 0:
                _raise_stale_revision(db, row_id, handle)
            if any_refs:
                audit(
                    db,
                    workspace_id,
                    "credential.force_field_delete",
                    resource_type="integration",
                    resource_id=str(row_id),
                    metadata={
                        "handle": handle,
                        "field": field,
                        "environment_id": env_id,
                        "references": refs,
                    },
                )

    db.commit()
    return DeleteEnvVarResponse(
        handle=handle,
        field=field,
        deleted=True,
        references=refs,
    )
