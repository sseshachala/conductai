"""Read-only inventory for legacy ``env_vars`` catch-all rows (#2054 Phase 3).

Discovery-only. The endpoint returns **metadata only** — never credential
values — so an admin can decide which fields to migrate to a proper
provider handle, which are legitimate arbitrary variables (safe as-is),
and which would collide with an existing row on reroute.

Guardrails from the epic:
- Metadata only — field names, suggested reroute, collision flag. No
  values, no fingerprints derived from values, no plaintext in logs.
- No writes. Migration is a separate, admin-approved operation.
- Workspace-scoped through ``get_workspace_id``; cross-tenant reads
  refused via ``require_permission("platform.credentials.manage")``.

The output feeds an operator UI or a scripted migration plan. Any
legitimate custom variable (``MY_CUSTOM_VAR`` etc.) stays in the
``env_vars`` bag — the epic explicitly warns against blindly unpacking
every row.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.crypto import decrypt
from app.core.database import get_db
from app.models.integration import Integration
from app.routers.env_vars import _ENV_VAR_MAP


router = APIRouter(prefix="/credentials", tags=["credentials"])


# ---------------------------------------------------------------------------
# Response DTOs
# ---------------------------------------------------------------------------


class SuggestedReroute(BaseModel):
    handle: str
    field: str


class CollisionDetail(BaseModel):
    """When rerouting would clash with an existing row."""
    handle: str
    field: str
    existing_integration_id: str
    # Whether the existing row already has this exact field populated
    # (hard collision) or just holds the target handle (soft — the field
    # slot is free, but the row identity contract still needs care).
    field_already_present: bool
    # True when the destination row's ciphertext failed to decrypt: we
    # can't tell whether the field is present or not, so migration must
    # not treat the slot as free. Operator has to unblock manually.
    destination_unreadable: bool = False


class InventoryFieldOut(BaseModel):
    name: str
    # Classification the operator should act on:
    #  - "reroutable" — canonical mapping exists and the target is free.
    #  - "collision"  — canonical mapping exists but target is occupied.
    #  - "needs_review" — no exact mapping. Includes case-insensitive
    #    matches (name differs from canonical only in case) and unknown
    #    provider-shaped names. Reviewer's contract: unmapped ≠ safe.
    #  - "unreadable" — the source row's ciphertext could not be decrypted;
    #    field name is best-effort and the operator must inspect manually.
    status: str
    suggested_reroute: SuggestedReroute | None
    collision: CollisionDetail | None
    # Present when we matched a canonical name only after case-normalising
    # the source. Never auto-migrate on a case-only match — the reviewer
    # explicitly said no blind uppercasing. Operator confirms.
    canonical_name_hint: str | None = None
    # When another source field in the same workspace inventory also
    # targets the same (handle, field), this field is flagged so migration
    # can't collapse two sources into one destination silently.
    many_to_one_conflict_with: list[str] = []


class InventoryEnvVarsRowOut(BaseModel):
    integration_id: str
    field_count: int
    fields: list[InventoryFieldOut]


class InventoryEnvironmentOut(BaseModel):
    environment_id: str | None
    environment_name: str | None
    env_vars_rows: list[InventoryEnvVarsRowOut]


class InventoryReport(BaseModel):
    total_env_vars_rows: int
    total_env_vars_fields: int
    reroutable_field_count: int
    # Fields we can't safely classify without operator input — see the
    # per-field ``status`` for the specific reason.
    needs_review_field_count: int
    collision_count: int
    unreadable_source_count: int
    environments: list[InventoryEnvironmentOut]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _target_row_for(
    db: Session,
    workspace_id: str,
    environment_id,
    handle: str,
) -> Integration | None:
    """Look up the row a reroute would land on. May be None if free."""
    return db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.environment_id == environment_id,
        Integration.handle == handle,
    ).first()


def _decrypt_fields(row: Integration) -> dict[str, str] | None:
    """Return the row's decrypted field names, or None if unreadable.

    Callers use ``None`` to mean "we can't tell what's in there" so
    downstream classification never silently treats an unreadable target
    as a free slot. Values are dropped immediately after keys are extracted.
    """
    if not row.encrypted_credentials:
        return {}
    try:
        blob = decrypt(row.encrypted_credentials) or {}
        return dict(blob) if isinstance(blob, dict) else {}
    except Exception:
        return None


def _classify_field(
    db: Session,
    workspace_id: str,
    environment_id,
    field_name: str,
    source_readable: bool,
) -> InventoryFieldOut:
    """Classify one env_vars bag field. Field names only.

    Rules (per reviewer contract):
    - Unmapped fields default to ``needs_review`` — never ``custom_variable``.
      The operator confirms which unmapped fields are legitimate custom
      variables; the inventory only surfaces facts.
    - Case-insensitive matches (e.g. ``github_token`` → ``GITHUB_TOKEN``)
      never auto-migrate. Flagged as ``needs_review`` with
      ``canonical_name_hint`` so the operator can decide.
    - Unreadable source blob → ``unreadable``. Migration must skip.
    - Collision destination row unreadable → destination_unreadable=True
      on the collision, so migration can't treat it as "field is free".
    """
    if not source_readable:
        return InventoryFieldOut(
            name=field_name,
            status="unreadable",
            suggested_reroute=None,
            collision=None,
        )

    mapped = _ENV_VAR_MAP.get(field_name)
    if mapped:
        target_handle, target_field = mapped
        suggestion = SuggestedReroute(handle=target_handle, field=target_field)
        existing = _target_row_for(db, workspace_id, environment_id, target_handle)
        if existing is None:
            return InventoryFieldOut(
                name=field_name,
                status="reroutable",
                suggested_reroute=suggestion,
                collision=None,
            )
        existing_fields = _decrypt_fields(existing)
        destination_unreadable = existing_fields is None
        return InventoryFieldOut(
            name=field_name,
            status="collision",
            suggested_reroute=suggestion,
            collision=CollisionDetail(
                handle=target_handle,
                field=target_field,
                existing_integration_id=str(existing.id),
                # An unreadable destination MUST NOT report the slot as free.
                field_already_present=(
                    True if destination_unreadable
                    else target_field in (existing_fields or {})
                ),
                destination_unreadable=destination_unreadable,
            ),
        )

    # No exact mapping. Try a case-insensitive match; if found, still
    # ``needs_review`` — reviewer explicitly disallowed blind uppercasing.
    upper = field_name.upper()
    if upper != field_name and upper in _ENV_VAR_MAP:
        return InventoryFieldOut(
            name=field_name,
            status="needs_review",
            suggested_reroute=None,
            collision=None,
            canonical_name_hint=upper,
        )
    # Truly unmapped. Reviewer contract: unmapped means "needs
    # classification", not "legitimate custom variable". Operator decides.
    return InventoryFieldOut(
        name=field_name,
        status="needs_review",
        suggested_reroute=None,
        collision=None,
    )


# ---------------------------------------------------------------------------
# GET — inventory across all environments in the workspace
# ---------------------------------------------------------------------------


@router.get("/env-vars/inventory", response_model=InventoryReport)
def inventory_env_vars(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.credentials.manage")),
) -> InventoryReport:
    """Return a metadata-only report of every ``env_vars`` catch-all row.

    Discovery for the #2054 Phase 3 cleanup — surfaces which fields have
    a canonical provider reroute, which don't (legitimate custom vars),
    and which would collide with an existing row on reroute. No values
    are returned or logged.
    """
    from app.models.environment import Environment

    env_vars_rows = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == "env_vars",
    ).order_by(Integration.environment_id, Integration.created_at).all()

    # Workspace-scoped env name lookup — the JOIN prevents a
    # malformed integration.environment_id from surfacing another
    # workspace's env metadata.
    env_ids = {r.environment_id for r in env_vars_rows if r.environment_id is not None}
    env_name_by_id: dict = {}
    if env_ids:
        for e in db.query(Environment).filter(
            Environment.id.in_(env_ids),
            Environment.workspace_id == workspace_id,
        ).all():
            env_name_by_id[e.id] = e.name

    per_env: dict = {}
    # First pass: classify every field independently.
    for row in env_vars_rows:
        env_id = row.environment_id
        bucket = per_env.setdefault(env_id, [])
        decrypted = _decrypt_fields(row)
        source_readable = decrypted is not None
        field_names = list((decrypted or {}).keys())
        fields_out: list[InventoryFieldOut] = [
            _classify_field(db, workspace_id, env_id, name, source_readable)
            for name in field_names
        ]
        bucket.append(InventoryEnvVarsRowOut(
            integration_id=str(row.id),
            field_count=len(fields_out),
            fields=fields_out,
        ))

    environments = [
        InventoryEnvironmentOut(
            environment_id=str(env_id) if env_id is not None else None,
            environment_name=env_name_by_id.get(env_id),
            env_vars_rows=rows,
        )
        for env_id, rows in per_env.items()
    ]

    # Second pass: many-to-one detection. If two source fields (across
    # any env_vars bag in the workspace) both suggest the same
    # ``(handle, field)`` destination, flag them so migration can't
    # collapse them silently. Reviewer's #5 defect: without this,
    # GITHUB_TOKEN and GITHUB_PAT both look independently reroutable.
    target_index: dict[tuple[str, str], list[str]] = {}
    for env in environments:
        for r in env.env_vars_rows:
            for f in r.fields:
                if f.suggested_reroute is None:
                    continue
                key = (f.suggested_reroute.handle, f.suggested_reroute.field)
                target_index.setdefault(key, []).append(f.name)
    for env in environments:
        for r in env.env_vars_rows:
            for f in r.fields:
                if f.suggested_reroute is None:
                    continue
                key = (f.suggested_reroute.handle, f.suggested_reroute.field)
                others = [n for n in target_index[key] if n != f.name]
                if others:
                    f.many_to_one_conflict_with = others
                    # A many-to-one is not safely reroutable even if the
                    # destination row itself doesn't exist yet.
                    if f.status == "reroutable":
                        f.status = "collision"

    total_rows = len(env_vars_rows)
    total_fields = sum(r.field_count for env in environments for r in env.env_vars_rows)
    reroutable = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.status == "reroutable"
    )
    needs_review = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.status == "needs_review"
    )
    collisions = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.status == "collision"
    )
    unreadable = sum(
        1
        for env in environments
        for r in env.env_vars_rows
        for f in r.fields
        if f.status == "unreadable"
    )

    return InventoryReport(
        total_env_vars_rows=total_rows,
        total_env_vars_fields=total_fields,
        reroutable_field_count=reroutable,
        needs_review_field_count=needs_review,
        collision_count=collisions,
        unreadable_source_count=unreadable,
        environments=environments,
    )
