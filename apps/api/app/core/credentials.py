from __future__ import annotations

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
