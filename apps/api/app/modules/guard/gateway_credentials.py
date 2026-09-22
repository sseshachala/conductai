"""Shared Vault credential resolution for canonical gateway profiles."""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.credentials import get_vault_credential
from app.models.environment import Environment


@dataclass(frozen=True)
class VaultCredentialRef:
    environment_id: str | None
    selector: str


def parse_vault_credential_ref(credential_ref: str | None) -> VaultCredentialRef | None:
    """Parse canonical refs while retaining legacy handle-only references."""
    if not credential_ref or not credential_ref.startswith("vault://"):
        return None
    parts = [part for part in credential_ref.removeprefix("vault://").strip("/").split("/") if part]
    if not parts:
        return None
    if len(parts) == 2:
        try:
            return VaultCredentialRef(environment_id=str(UUID(parts[0])), selector=parts[1])
        except ValueError:
            pass
    return VaultCredentialRef(environment_id=None, selector=parts[-1])


def _default_environment_id(db: Session, workspace_id: str) -> str | None:
    row = db.query(Environment).filter(
        Environment.workspace_id == workspace_id,
        Environment.name == "Default",
    ).first()
    return str(row.id) if row else None


def resolve_gateway_key(
    db: Session,
    workspace_id: str,
    credential_ref: str | None,
    provider: str,
    environment_id: str | None,
) -> str | None:
    """Resolve a gateway key from environment Vault data, never profile JSON."""
    parsed = parse_vault_credential_ref(credential_ref)
    if parsed is None:
        return None
    vault_id = parsed.environment_id or environment_id or _default_environment_id(db, workspace_id)
    if not vault_id:
        return None
    creds = get_vault_credential(db, workspace_id, vault_id, parsed.selector)
    key = (
        creds.get("LLM_UPSTREAM_API_KEY")
        or creds.get("api_key")
        or creds.get(f"{provider.upper()}_API_KEY")
        or creds.get(f"{provider.lower()}_api_key")
    )
    if key:
        return key
    legacy_env = get_vault_credential(db, workspace_id, vault_id, "env_vars")
    return legacy_env.get("PROXY_CONFIG_LLM_UPSTREAM_API_KEY")


def resolve_vendor_key(
    db: Session,
    workspace_id: str,
    credential_ref: str | None,
    vendor_key_names: tuple[str, ...],
    environment_id: str | None,
) -> str | None:
    """Fetch a vendor-side API key from the SAME vault entry as the
    primary integration key.

    Used for Helicone-style two-key auth where a single vault handle
    holds ``HELICONE_API_KEY`` (integration/observability key) AND the
    upstream vendor key (``OPENAI_API_KEY`` or ``ANTHROPIC_API_KEY``)
    in the same credential blob. Returns the first ``vendor_key_names``
    match, or ``None`` if none present — the caller decides whether
    None is a fail-closed 503 (Helicone) or a benign no-op.
    """
    if not vendor_key_names:
        return None
    parsed = parse_vault_credential_ref(credential_ref)
    if parsed is None:
        return None
    vault_id = parsed.environment_id or environment_id or _default_environment_id(db, workspace_id)
    if not vault_id:
        return None
    creds = get_vault_credential(db, workspace_id, vault_id, parsed.selector)
    return next((creds.get(name) for name in vendor_key_names if creds.get(name)), None)
