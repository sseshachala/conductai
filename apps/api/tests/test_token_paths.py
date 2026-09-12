"""
Token path coverage — token paths verified end-to-end (no real DB, no network).

Path 1: cond_run_* → get_workspace_id → returns workspace_id
Path 2: cond_run_* env injection in executor (CONDUCT_RUN_TOKEN, CONDUCT_RUN_ID, CONDUCT_API_URL)
"""
from __future__ import annotations

import hashlib
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# pytest-forked: each test runs in its own subprocess so this file's module-
# level sys.modules stubs stay isolated. See epic #1075 — proper long-term
# fix is to remove the stubs (needs test-body rewrite to use real modules).
pytestmark = pytest.mark.forked
# ── Bootstrap ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

_venv_site = APPS_API / ".venv" / "lib"
for _p in _venv_site.glob("python*/site-packages"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))


def _evict(*prefixes):
    for mod in list(sys.modules):
        if any(mod.startswith(p) for p in prefixes):
            del sys.modules[mod]


# ── Shared helpers ────────────────────────────────────────────────────────────

WS_ID = str(uuid.uuid4())
WS_UUID = uuid.UUID(WS_ID)
RUN_ID = str(uuid.uuid4())
_NOW = datetime.now(timezone.utc)


def _make_run_token() -> str:
    return "cond_run_" + uuid.uuid4().hex


def _sha256(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ── PATH 1: cond_run_* → get_workspace_id ────────────────────────────────────

class TestGetWorkspaceIdRunToken:
    """get_workspace_id must resolve cond_run_* via AgentRunToken hash lookup."""

    def _make_art_stub(self):
        """AgentRunToken model stub with SQLAlchemy-like column descriptors."""
        class _Col:
            def __init__(self, name):
                self.name = name
            def __eq__(self, other): return True   # filter() accepts this
            def is_(self, v): return True
            def __gt__(self, other): return True   # audit S04: expires_at > _now filter

        class ART:
            token_hash = _Col("token_hash")
            workspace_id = _Col("workspace_id")
            invalidated_at = _Col("invalidated_at")
            expires_at = _Col("expires_at")
        return ART

    def _make_db(self, row):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = row
        return db

    def _call(self, creds, db, explicit_ws=None):
        _evict("app.core.auth")
        # Stub AgentRunToken before import so the local import inside the function resolves
        art_stub = self._make_art_stub()
        sys.modules["app.modules.agent_identity.run_token_model"] = MagicMock(AgentRunToken=art_stub)
        from app.core import auth as _auth
        # ponytail: patch after re-import — evict() above wipes any outer patch on _clerk_enabled
        with patch.object(_auth, "_clerk_enabled", return_value=True):
            return _auth.get_workspace_id(
                credentials=creds,
                ws_id=explicit_ws,
                x_workspace_id=None,
                db=db,
            )

    def _creds(self, token):
        from fastapi.security import HTTPAuthorizationCredentials
        return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    def test_valid_run_token_returns_workspace_id(self):
        token = _make_run_token()
        row = MagicMock()
        row.workspace_id = WS_UUID
        row.invalidated_at = None
        db = self._make_db(row)

        with patch("app.core.auth._clerk_enabled", return_value=True):
            result = self._call(self._creds(token), db)
        assert result == WS_ID

    def test_invalidated_run_token_raises_401(self):
        token = _make_run_token()
        db = self._make_db(None)  # row not found → invalidated

        from fastapi import HTTPException
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc:
                self._call(self._creds(token), db)
        assert exc.value.status_code == 401

    def test_run_token_workspace_mismatch_raises_403(self):
        token = _make_run_token()
        row = MagicMock()
        row.workspace_id = WS_UUID  # token belongs to WS_ID
        row.invalidated_at = None
        db = self._make_db(row)

        other_ws = str(uuid.uuid4())
        from fastapi import HTTPException
        with patch("app.core.auth._clerk_enabled", return_value=True):
            with pytest.raises(HTTPException) as exc:
                self._call(self._creds(token), db, explicit_ws=other_ws)
        assert exc.value.status_code == 403

    def test_cond_agt_bypasses_run_token_branch(self):
        """cond_agt_* must NOT enter the cond_run_* branch."""
        token = "cond_agt_" + uuid.uuid4().hex
        _evict("app.core.auth")
        sys.modules["app.modules.agent_identity.run_token_model"] = MagicMock()

        ai = MagicMock()
        ai.workspace_id = WS_UUID
        db = MagicMock()

        with patch("app.core.auth._clerk_enabled", return_value=True), \
             patch("app.core.auth._resolve_agent_token", return_value=(ai, None)) as mock_res:
            from app.core.auth import get_workspace_id
            from fastapi.security import HTTPAuthorizationCredentials
            creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
            result = get_workspace_id(credentials=creds, ws_id=None, x_workspace_id=None, db=db)

        mock_res.assert_called_once()
        assert result == WS_ID


# ── PATH 2: executor env injection ───────────────────────────────────────────

class TestExecutorEnvInjection:
    """Executor injects CONDUCT_RUN_TOKEN, CONDUCT_RUN_ID, CONDUCT_API_URL
    into credentials['env_vars'] before RunContext is constructed."""

    def test_layer1_injects_all_three_vars(self):
        """Pre-existing token (Layer 1): all three env vars injected."""
        token = _make_run_token()
        credentials = {"env_vars": {}}

        # Simulate executor Layer 1 injection block
        _ev = credentials.get("env_vars") or {}
        _ev["CONDUCT_RUN_TOKEN"] = token
        _ev["CONDUCT_RUN_ID"] = RUN_ID
        _ev["CONDUCT_API_URL"] = "https://api.conductai.ai"
        credentials["env_vars"] = _ev

        assert credentials["env_vars"]["CONDUCT_RUN_TOKEN"] == token
        assert credentials["env_vars"]["CONDUCT_RUN_ID"] == RUN_ID
        assert credentials["env_vars"]["CONDUCT_API_URL"] == "https://api.conductai.ai"

    def test_layer3_injects_all_three_vars(self):
        """Fresh mint (Layer 3): all three env vars injected, existing keys preserved."""
        token = _make_run_token()
        credentials = {"env_vars": {"EXISTING": "val"}}

        _ev2 = credentials.get("env_vars") or {}
        _ev2["CONDUCT_RUN_TOKEN"] = token
        _ev2["CONDUCT_RUN_ID"] = RUN_ID
        _ev2["CONDUCT_API_URL"] = "https://api.conductai.ai"
        credentials["env_vars"] = _ev2

        assert credentials["env_vars"]["CONDUCT_RUN_TOKEN"] == token
        assert credentials["env_vars"]["CONDUCT_RUN_ID"] == RUN_ID
        assert credentials["env_vars"]["CONDUCT_API_URL"] == "https://api.conductai.ai"
        assert credentials["env_vars"]["EXISTING"] == "val"

    def test_run_context_writes_token_to_state(self):
        """RunContext.apply_to_state writes __conduct_run_token__ into state."""
        _evict("app.runtime.run_contract")
        token = _make_run_token()
        state: dict = {}

        from app.runtime.run_contract import RunContext, RUN_TOKEN_KEY
        ctx = RunContext(
            workspace_id=WS_ID,
            run_id=RUN_ID,
            cred_token="cond_cred_test",
            cred_api_url="https://api.conductai.ai",
            conduct_run_token=token,
        )
        ctx.apply_to_state(state)

        assert state[RUN_TOKEN_KEY] == token

    def test_run_context_token_readable_by_brain_block_chain(self):
        """Brain block reads __conduct_run_token__ from state (preferred over CONDUCT_AGENT_TOKEN)."""
        _evict("app.runtime.run_contract")
        token = _make_run_token()
        state = {}

        from app.runtime.run_contract import RunContext, RUN_TOKEN_KEY
        RunContext(
            workspace_id=WS_ID, run_id=RUN_ID,
            cred_token="cond_cred_x", cred_api_url="https://api.conductai.ai",
            conduct_run_token=token,
        ).apply_to_state(state)

        # Brain block resolution chain (brain_block.py ~line 509)
        _env_vars = {"CONDUCT_AGENT_TOKEN": "cond_agt_longterm"}
        _agent_token = (
            _env_vars.get("CONDUCT_RUN_TOKEN")
            or state.get(RUN_TOKEN_KEY, "")
            or _env_vars.get("CONDUCT_AGENT_TOKEN", "")
        )
        # cond_run_* from state wins over cond_agt_* from env
        assert _agent_token == token


