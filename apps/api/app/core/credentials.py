from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.crypto import decrypt
from app.models.integration import Integration


class CredentialStore:
    """
    Dict-like wrapper around decrypted credentials.
    repr()/str() never expose plaintext — only handle names.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    def __repr__(self) -> str:
        return f"CredentialStore(handles={list(self._data.keys())})"

    def __str__(self) -> str:
        return self.__repr__()


def get_credential(db, workspace_id: str, handle: str, environment_id=None) -> dict:
    """Fetch and decrypt a single integration by handle. Returns {} if not found."""
    q = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == handle,
    )
    if environment_id:
        q = q.filter(Integration.environment_id == environment_id)
    row = q.first()
    if not row or not row.encrypted_credentials:
        return {}
    return decrypt(row.encrypted_credentials) or {}


def mint_cred_token(
    db,
    run_id: str,
    workspace_id: str,
    allowed_handles: list[str],
    environment_id: str | None = None,
    ttl_seconds: int = 3600,
) -> str:
    """
    Mint a short-lived retrieval token scoped to a run + handle allowlist.
    Both proxy-mode subprocesses and sandbox containers use the same token
    to call POST /credentials/creds/retrieve — no divergent credential injection paths.
    """
    from sqlalchemy import text as _sql
    token = "cond_cred_" + secrets.token_hex(24)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    max_uses = max(len(allowed_handles) * 3, 3)  # 3× handles — covers retries + parallel blocks
    db.execute(
        _sql("""
            INSERT INTO cred_retrieval_tokens
                (token, run_id, workspace_id, environment_id, allowed_handles, expires_at, max_uses)
            VALUES (:token, :run_id, :ws, :env_id, :handles, :exp, :max_uses)
        """),
        {
            "token": token,
            "run_id": run_id,
            "ws": workspace_id,
            "env_id": environment_id,
            "handles": allowed_handles,
            "exp": expires_at,
            "max_uses": max_uses,
        },
    )
    db.commit()
    return token


def retrieve_credential(db, cred_token: str, handle: str) -> dict | None:
    """
    Validate a retrieval token and return decrypted credential for the requested handle.
    Returns None if token is invalid, expired, or handle not in allowlist.
    """
    from sqlalchemy import text as _sql
    # Atomic increment + fetch — prevents race between concurrent block fetches
    row = db.execute(
        _sql("""
            UPDATE cred_retrieval_tokens
            SET used_count = used_count + 1
            WHERE token = :token
              AND expires_at > now()
              AND used_count < max_uses
            RETURNING workspace_id, environment_id, allowed_handles, expires_at, used_count, max_uses
        """),
        {"token": cred_token},
    ).fetchone()

    if not row:
        return None  # not found, expired, or rate limit exceeded
    if handle not in (row.allowed_handles or []):
        db.rollback()
        return None
    db.commit()

    return get_credential(db, row.workspace_id, handle, row.environment_id)


def fetch_credential(cred_token: str, handle: str, api_url: str) -> dict:
    """HTTP call to broker. Used by blocks running inside a run context."""
    import httpx
    resp = httpx.post(
        f"{api_url}/credentials/creds/retrieve",
        json={"handle": handle},
        headers={"X-Cred-Token": cred_token},
        timeout=5.0,
    )
    if resp.status_code == 200:
        return resp.json()
    return {}


def get_all_credentials(db, workspace_id: str, environment_id=None) -> CredentialStore:
    """
    Fetch and decrypt all integrations for a workspace.

    Resolution order:
      1. Credentials for the specified environment_id
      2. Fallback: merge missing handles from the Default environment
    Same-handle dicts are merged (env_vars pattern).
    """
    from app.models.environment import Environment as _Env

    def _load_rows(env_id) -> list:
        return db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.environment_id == env_id,
        ).all()

    def _merge(raw: dict, rows: list, overwrite: bool = True) -> None:
        for row in rows:
            if not row.encrypted_credentials:
                continue
            decrypted = decrypt(row.encrypted_credentials) or {}
            if row.handle in raw and isinstance(raw[row.handle], dict) and isinstance(decrypted, dict):
                # ponytail: merge same-handle dicts (env_vars + agent_identity both use handle="env_vars")
                raw[row.handle] = {**raw[row.handle], **decrypted} if overwrite else {**decrypted, **raw[row.handle]}
            elif overwrite or row.handle not in raw:
                raw[row.handle] = decrypted

    raw: dict[str, Any] = {}

    default_env = db.query(_Env).filter(
        _Env.workspace_id == workspace_id,
        _Env.name == "Default",
    ).first()

    if environment_id:
        _merge(raw, _load_rows(environment_id))
        # Merge missing handles from Default
        if default_env and str(default_env.id) != str(environment_id):
            _merge(raw, _load_rows(default_env.id), overwrite=False)
    elif default_env:
        _merge(raw, _load_rows(default_env.id))

    result = CredentialStore(raw)
    del raw
    return result

def resolve_token(token: str, db) -> dict | None:
    """
    Single dispatcher for all cond_* token types — routes by prefix.

    cond_cred_*  → cred_retrieval_tokens  (run-scoped credential access)
    cond_agt_*   → agent_identities       (session identity token)
    cond_api_*   → agent_identities       (long-lived OAuth token)

    Returns a dict with token metadata, or None if invalid/expired.
    """
    if token.startswith("cond_cred_"):
        from sqlalchemy import text as _sql
        row = db.execute(
            _sql("""
                SELECT token, run_id, workspace_id, environment_id,
                       allowed_handles, expires_at, used_count, max_uses
                FROM cred_retrieval_tokens WHERE token = :token
            """),
            {"token": token},
        ).fetchone()
        if not row:
            return None
        return {
            "type": "cred",
            "run_id": row.run_id,
            "workspace_id": row.workspace_id,
            "environment_id": row.environment_id,
            "allowed_handles": row.allowed_handles,
            "expires_at": row.expires_at,
            "used_count": row.used_count,
            "max_uses": row.max_uses,
        }

    if token.startswith(("cond_agt_", "cond_api_")):
        from app.modules.guard.routers.mcp import resolve_agent_token
        identity = resolve_agent_token(token, db)
        if not identity:
            return None
        return {
            "type": "agent",
            "developer_id": identity.get("developer_id"),
            "developer_email": identity.get("developer_email"),
            "workspace_id": identity.get("workspace_id"),
            "token_name": identity.get("token_name"),
        }

    if token.startswith("cond_run_"):
        import hashlib as _h
        from sqlalchemy import text as _sql
        token_hash = _h.sha256(token.encode()).hexdigest()
        row = db.execute(
            _sql("""
                SELECT art.run_id, art.workspace_id, art.agent_identity_id,
                       art.created_at, art.first_used_at, art.invalidated_at,
                       ai.name as identity_name
                FROM agent_run_tokens art
                LEFT JOIN agent_identities ai ON ai.id = art.agent_identity_id::uuid
                WHERE art.token_hash = :hash
            """),
            {"hash": token_hash},
        ).fetchone()
        if not row:
            return None
        return {
            "type": "run",
            "run_id": row.run_id,
            "workspace_id": str(row.workspace_id),
            "agent_identity_id": row.agent_identity_id,
            "identity_name": row.identity_name,
            "created_at": row.created_at,
            "first_used_at": row.first_used_at,
            "invalidated": row.invalidated_at is not None,
        }

    return None
