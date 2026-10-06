"""Stateless client-label continuity, not cached authentication or authorization."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from typing import NamedTuple
from uuid import UUID, uuid4

from app.core.config import settings

SURFACES = frozenset({
    "chatgpt", "chatgpt-work", "claude.ai", "claude-code", "claude-desktop",
    "codex", "copilot-cli", "vscode", "cursor", "windsurf",
})


class SurfaceSession(NamedTuple):
    surface: str
    session_id: str


def _signature(nonce: str, surface: str, workspace: str, actor: str | None, token: str) -> str:
    # User-bound metadata survives access-token rotation. Service callers have
    # no user subject, so their label is bound to the credential fingerprint.
    principal = ["user", actor] if actor else ["service", hashlib.sha256(token.encode()).hexdigest()]
    payload = json.dumps([nonce, surface, workspace, principal], separators=(",", ":")).encode()
    key = hmac.digest(settings.encryption_key.encode(), b"conduct.mcp.surface-session.v1", "sha256")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def issue(surface: str, workspace: str, actor: str | None, token: str) -> str:
    nonce = str(uuid4())
    if surface not in SURFACES:
        return nonce
    return f"mcp1:{nonce}:{surface}:{_signature(nonce, surface, workspace, actor, token)}"


def resolve(session_id: str, workspace: str, actor: str | None, token: str) -> SurfaceSession | None:
    if len(session_id) > 255:
        return None
    parts = session_id.split(":")
    if len(parts) != 4 or parts[0] != "mcp1":
        return None
    _, nonce, surface, signature = parts
    if surface not in SURFACES or not re.fullmatch(r"[0-9a-f]{64}", signature):
        return None
    try:
        if str(UUID(nonce)) != nonce:
            return None
    except ValueError:
        return None
    if hmac.compare_digest(signature, _signature(nonce, surface, workspace, actor, token)):
        return SurfaceSession(surface, nonce)
    return None
