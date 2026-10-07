"""Shared bootstrap, stubs and token/session builders for the Agent
Identity auth unit tests (``test_agent_identity_auth*.py``).

Importing this module performs the path + env bootstrap, so test modules
must import it before any ``app.*`` import.
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

# ── Path + env bootstrap (must precede all app imports) ─────────────────────

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Add venv site-packages so SQLAlchemy / cryptography are importable
_venv_site = APPS_API / ".venv" / "lib"
_venv_paths_added: list[str] = []
for _p in _venv_site.glob("python*/site-packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
        _venv_paths_added.append(str(_p))

# ── Constants shared across tests ────────────────────────────────────────────

_WS_ID = str(uuid.uuid4())
_WS_UUID = uuid.UUID(_WS_ID)
_USER_ID = "user_clerk_abc123"
_AGT_PREFIX_LEN = len("cond_agt_") + 4   # 13
_API_PREFIX_LEN = len("cond_api_") + 4   # 13


# ── AgentIdentity stub ───────────────────────────────────────────────────────
# resolve_agent_token does:
#   db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix)
# AgentIdentity.token_prefix must behave like a SQLAlchemy column descriptor
# (supports ==) when used in a filter expression. We stub it with a simple
# sentinel so the MagicMock DB chain resolves cleanly.

class _ColDescriptor:
    """Minimal column descriptor: supports == for use in filter()."""
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return f"{self.name}=={other!r}"   # truthy string; MagicMock accepts it


class _AgentIdentityStub:
    """Stub that provides column descriptors without a real DB engine."""
    token_prefix = _ColDescriptor("token_prefix")


class _GuardConfigStub:
    """Stub for GuardConfig used in mcp_endpoint filter expressions."""
    workspace_id = _ColDescriptor("workspace_id")


class _AgentIdentityModelStub:
    """Stub for AgentIdentity used in oauth_member_token filter expressions.
    Also acts as a constructor so the `AgentIdentity(...)` call inside the
    function returns a usable MagicMock instead of raising StopIteration."""
    id = _ColDescriptor("id")

    def __call__(self, **kwargs):
        row = MagicMock()
        for k, v in kwargs.items():
            setattr(row, k, v)
        return row
    __tablename__ = "agent_identities"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_ai_row(token: str, workspace_id: str | None = None, created_by: str | None = None, token_name: str | None = None, expires_at=None):
    """Return a minimal AgentIdentity-like object.

    expires_at defaults to None so resolve_agent_token treats the row as
    non-expiring (matches cond_api_ behaviour). Pass a past datetime to
    simulate an expired session token.
    """
    row = MagicMock()
    row.id = str(uuid.uuid4())
    row.token_prefix = token[:_AGT_PREFIX_LEN]
    row.workspace_id = uuid.UUID(workspace_id) if workspace_id else _WS_UUID
    row.created_by_clerk_user_id = created_by
    row.token_name = token_name
    row.name = token_name or "test-token"
    row.expires_at = expires_at
    return row


def _db_with_ai(ai_row, member_row=None):
    """Build a mock Session that returns ai_row from AgentIdentity query
    and member_row from the raw SQL execute call."""
    db = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = [ai_row]
    db.query.return_value.filter.return_value = query_result

    execute_result = MagicMock()
    execute_result.fetchone.return_value = member_row
    db.execute.return_value = execute_result
    return db


def _db_no_ai():
    """Session that returns no AgentIdentity rows."""
    db = MagicMock()
    query_result = MagicMock()
    query_result.all.return_value = []
    db.query.return_value.filter.return_value = query_result
    return db


def _db_for_legacy(member_row):
    """Session for legacy bare-hex / guard-mt-* path (no query(), only execute())."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    execute_result = MagicMock()
    execute_result.fetchone.return_value = member_row
    db.execute.return_value = execute_result
    return db


def _agt_token():
    """Return a random cond_agt_* token that never collides with the
    session-credential prefix (``cond_agt_s1_``).

    ``secrets.token_urlsafe`` uses a 64-char alphabet
    (``A-Za-z0-9-_``). Once every ~262k invocations the random tail
    starts with ``s1_`` — the resulting ``cond_agt_s1_...`` matches
    ``SESSION_ACCESS_PREFIX`` and routes ``resolve_agent_token`` down
    the session path, where the test's MagicMock ``db`` produces
    a MagicMock ``expires_at`` that then blows up the ``<=``
    comparison in ``app/core/auth.py``. Loop until the collision
    doesn't happen (#2162). Retry cost is negligible; the loop body
    runs at most twice in practical terms.
    """
    import secrets
    while True:
        tail = secrets.token_urlsafe(32)
        if not tail.startswith("s1_"):
            return "cond_agt_" + tail


def _api_token():
    import secrets
    return "cond_api_" + secrets.token_urlsafe(32)


# ── Patch target for AgentIdentity inside resolve_agent_token ────────────────
# auth.py does `from app.modules.agent_identity.models import AgentIdentity`
# inside the function body, so we patch the module attribute.
_AI_PATCH = "app.modules.agent_identity.models.AgentIdentity"


# Remove the venv paths we added so subsequent tests resolve from normal paths.
# (Was at the end of the original single test module; the net effect -- paths
# present only while the module is being imported -- is unchanged.)
for _venv_p in _venv_paths_added:
    try:
        sys.path.remove(_venv_p)
    except ValueError:
        pass
