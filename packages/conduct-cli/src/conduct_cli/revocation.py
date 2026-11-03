"""Local kill switch: remember that an admin deactivated this agent identity.

When ``/auth/refresh`` answers 401 with ``X-Conduct-Identity-State: deactivated``
the identity was turned off by a workspace admin. The marker is bound to the
agent token that was rejected, so it stops applying as soon as ``conduct login``
stores a different token. Expired or unknown tokens never set it.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

IDENTITY_STATE_HEADER = "X-Conduct-Identity-State"
MARKER_PATH = Path.home() / ".conduct" / "identity-revoked.json"

BLOCK_MESSAGE = (
    "[ConductGuard] This agent identity was deactivated by your workspace admin "
    "(kill switch). All tool calls are blocked. If access was restored, run `conduct login`."
)


def _fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_deactivation(error) -> bool:
    """True when an HTTP error is the server's explicit deactivation signal."""
    headers = getattr(error, "headers", None)
    try:
        state = headers.get(IDENTITY_STATE_HEADER) if headers is not None else None
    except Exception:
        return False
    return getattr(error, "code", None) == 401 and (state or "").lower() == "deactivated"


def mark_revoked(token: str | None) -> None:
    if not token:
        return
    try:
        MARKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        MARKER_PATH.write_text(json.dumps({"credential": _fingerprint(token), "at": time.time()}))
        MARKER_PATH.chmod(0o600)
    except OSError:
        pass


def is_revoked(token: str | None) -> bool:
    """True while the current token is the one the server reported deactivated."""
    try:
        marker = json.loads(MARKER_PATH.read_text())
    except (OSError, ValueError):
        return False
    if token and marker.get("credential") == _fingerprint(token):
        return True
    MARKER_PATH.unlink(missing_ok=True)
    return False
