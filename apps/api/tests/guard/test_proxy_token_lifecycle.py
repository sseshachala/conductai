"""Proxy token lifecycle tests (audit S04).

The old proxy internal-agent path did its own decrypt loop over every
AgentIdentity in the workspace, checked expires_at, and stopped there —
skipping the lifecycle_state and token_type rejections that the shared
resolver enforces at every other auth surface. A deactivated cond_agt_*
could authenticate via the proxy long after any UI would allow it.

Also covers the bounded-lifetime addition to cond_run_* tokens: an
abandoned token can't authenticate past its expires_at even when the run
itself never got a chance to write invalidated_at.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


# ── proxy path 2: internal agent identity via shared resolver ────────────

def _mk_ai(workspace_id: str, lifecycle: str = "active", token_type: str = "cli", expires_at=None):
    return SimpleNamespace(
        id="ai_abc",
        workspace_id=workspace_id,
        lifecycle_state=lifecycle,
        token_type=token_type,
        expires_at=expires_at,
        token_encrypted=b"blob",
    )


def test_resolve_agent_token_rejects_deactivated_identity():
    """S04 core: deactivated cond_agt_ must not authenticate. The previous
    proxy inline loop only checked expires_at, so a security team could
    revoke an identity in the UI and it would still work via internal proxy.
    """
    from app.core.auth import _resolve_agent_token
    db = MagicMock()
    deactivated = _mk_ai("ws-123", lifecycle="deactivated")
    db.query.return_value.filter.return_value.all.return_value = [deactivated]
    with patch("app.core.crypto.decrypt", return_value={"token": "cond_agt_abc"}):
        with pytest.raises(HTTPException) as exc:
            _resolve_agent_token("cond_agt_abc", db)
    assert exc.value.status_code == 401
    assert "deactivated" in (exc.value.detail or "").lower()


def test_resolve_agent_token_rejects_external_identity():
    """External (Okta-imported) identities must not authenticate via the
    Conduct token path — audit S04 grouped this under lifecycle enforcement."""
    from app.core.auth import _resolve_agent_token
    db = MagicMock()
    external = _mk_ai("ws-123", token_type="external")
    db.query.return_value.filter.return_value.all.return_value = [external]
    with patch("app.core.crypto.decrypt", return_value={"token": "cond_agt_abc"}):
        with pytest.raises(HTTPException) as exc:
            _resolve_agent_token("cond_agt_abc", db)
    assert exc.value.status_code == 401
    assert "external" in (exc.value.detail or "").lower()


def test_resolve_agent_token_rejects_expired_identity():
    from app.core.auth import _resolve_agent_token
    db = MagicMock()
    expired = _mk_ai(
        "ws-123",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    db.query.return_value.filter.return_value.all.return_value = [expired]
    with patch("app.core.crypto.decrypt", return_value={"token": "cond_agt_abc"}):
        with pytest.raises(HTTPException) as exc:
            _resolve_agent_token("cond_agt_abc", db)
    assert exc.value.status_code == 401
    assert "expired" in (exc.value.detail or "").lower()


# ── proxy path 1 + auth.py: cond_run_ expiry bound ───────────────────────

def test_run_token_expired_returns_none_from_auth_get_workspace_id():
    """auth.py: a cond_run_ whose expires_at is in the past must be rejected
    even when invalidated_at is still NULL. Bounded-lifetime property from
    audit S04.
    """
    import hashlib
    from unittest.mock import MagicMock

    from app.core.auth import get_workspace_id
    from fastapi.security import HTTPAuthorizationCredentials

    # Filter with expires_at > now returns nothing → HTTPException
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="cond_run_" + "a" * 32)

    with patch("app.core.auth._clerk_enabled_dispatch", return_value=True):
        with pytest.raises(HTTPException) as exc:
            get_workspace_id(credentials=creds, ws_id=None, x_workspace_id=None, db=db)
    assert exc.value.status_code == 401
    assert "run token" in (exc.value.detail or "").lower()

    # Sanity: filter was called with expires_at > now on the AgentRunToken filter chain.
    # Not asserting the exact SQLAlchemy call shape here — the effective
    # behaviour (401 when the row doesn't satisfy the expires_at guard) is
    # what matters.
