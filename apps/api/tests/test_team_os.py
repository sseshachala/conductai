"""
Tests for AI Rollout (epic #961) — Team OS instruction management API.

Covers:
  GET  /team-os/instructions              — empty defaults, existing row
  POST /team-os/instructions              — first publish (v1), re-publish bump (v4)
  GET  /team-os/instructions/version      — returns version when row exists
  GET  /team-os/instructions/adoption     — per-member sync status list

Uses TestClient with mocked DB session. No real DB or network.
"""
from __future__ import annotations

# pytest-forked: each test runs in its own subprocess so this file's module-
# level sys.modules stubs stay isolated. See epic #1075 — proper long-term
# fix is to remove the stubs (needs test-body rewrite to use real modules).
import pytest
pytestmark = pytest.mark.forked

import os
import sys
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Env vars before any app import ───────────────────────────────────────────
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# ── Stub app.core.config ─────────────────────────────────────────────────────
_cfg_stub = types.ModuleType("app.core.config")
_cfg_stub.settings = MagicMock(
    database_url="postgresql://test:test@localhost:5432/test_marshal",
    redis_url="redis://localhost:6379",
    sentry_dsn="",
    environment="test",
    log_level="INFO",
    clerk_secret_key="",
    clerk_frontend_api="",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    sqlalchemy_database_url="postgresql://test:test@localhost:5432/test_marshal",
    allowed_egress_hosts=[],
)
sys.modules.setdefault("app.core.config", _cfg_stub)

# ── Stub app.core.database ────────────────────────────────────────────────────
from sqlalchemy.orm import declarative_base as _decl_base  # noqa: E402

_db_mod = types.ModuleType("app.core.database")
_db_mod.Base = _decl_base()
_db_mod.SessionLocal = MagicMock()
_db_mod.get_db = MagicMock()
sys.modules.setdefault("app.core.database", _db_mod)

# ── Pre-import models to resolve FK relationships ─────────────────────────────
import app.models.environment  # noqa: F401, E402
import app.models.project      # noqa: F401, E402
import app.models.run          # noqa: F401, E402
import app.models.workspace    # noqa: F401, E402

# ── Import FastAPI app and dependency refs ────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.auth import (  # noqa: E402
    get_workspace_id,
    get_user_id,
    require_permission,
)

# ── Constants ─────────────────────────────────────────────────────────────────
WS_ID  = "00000000-0000-0000-0000-000000000099"
USER_ID = "user_test_team_os"
_NOW    = datetime(2026, 7, 22, 10, 0, 0, tzinfo=timezone.utc)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _override_db(db_mock):
    def _inner():
        yield db_mock
    return _inner


def _noop_permission(perm):
    async def _check():
        return "admin"
    return _check


def _make_client(db_mock):
    """Build a TestClient with all auth deps and require_permission bypassed."""
    app.dependency_overrides[get_db] = _override_db(db_mock)
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[get_user_id] = lambda: USER_ID
    app.dependency_overrides[require_permission] = _noop_permission
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_workspace_id, None)
    app.dependency_overrides.pop(get_user_id, None)
    app.dependency_overrides.pop(require_permission, None)


def _row(content: str, version: str, updated_at=None, updated_by: str = "admin@example.com"):
    """Build a MagicMock row matching the SELECT in _get_instructions."""
    r = MagicMock()
    r.content = content
    r.version = version
    r.updated_at = updated_at or _NOW
    r.updated_by = updated_by
    return r


def _version_row(version: str, updated_at=None):
    r = MagicMock()
    r.version = version
    r.updated_at = updated_at or _NOW
    return r


def _db_returning(fetchone_result, execute_count: int = 1):
    """
    Return a db mock where every .execute().fetchone() returns fetchone_result.
    Works for repeated calls (GET then POST then GET).
    """
    result_mock = MagicMock()
    result_mock.fetchone.return_value = fetchone_result
    db = MagicMock()
    db.execute.return_value = result_mock
    return db


# ── GET /team-os/instructions — empty ────────────────────────────────────────

class TestGetInstructionsEmpty:
    def test_returns_empty_defaults_when_no_row(self):
        db = _db_returning(None)
        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["content"]  # non-empty default instructions
            assert data["version"] == "v1"
            assert data["updated_at"] is None
            assert data["updated_by"] is None
        finally:
            _teardown()


# ── GET /team-os/instructions — existing row ──────────────────────────────────

class TestGetInstructionsExisting:
    def test_returns_stored_content_and_version(self):
        row = _row(
            content="## AI Policy\nNo secrets in prompts.\n",
            version="v3",
            updated_by="lead@example.com",
        )
        db = _db_returning(row)
        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["content"] == "## AI Policy\nNo secrets in prompts.\n"
            assert data["version"] == "v3"
            assert data["updated_by"] == "lead@example.com"
        finally:
            _teardown()


# ── POST /team-os/instructions — first publish ────────────────────────────────

class TestPublishInstructionsFirst:
    def test_first_publish_creates_with_v1(self):
        # fetchone returns None twice: once for version check, once for re-fetch
        result_mock = MagicMock()
        result_mock.fetchone.side_effect = [
            None,   # SELECT version → no existing row → new_version will be "v1"
            None,   # _get_instructions re-fetch after INSERT (returns empty defaults)
        ]
        db = MagicMock()
        db.execute.return_value = result_mock

        client = _make_client(db)
        try:
            with patch("app.routers.team_os.get_clerk_user_email", return_value="admin@example.com"):
                r = client.post(
                    "/team-os/instructions",
                    json={"content": "## Rules\nUse guard_check.\n"},
                    headers={"x-workspace-id": WS_ID},
                )
            assert r.status_code == 200, r.text
            # db.execute must have been called at least twice (SELECT + INSERT)
            assert db.execute.call_count >= 2, "Expected SELECT and INSERT calls"
            db.commit.assert_called_once()
            # When no existing row, _get_instructions returns v1 default
            data = r.json()
            assert data["version"] == "v1"
        finally:
            _teardown()


# ── POST /team-os/instructions — re-publish bumps version ─────────────────────

class TestPublishInstructionsRebump:
    def test_republish_bumps_v3_to_v4(self):
        existing_version_row = MagicMock()
        existing_version_row.version = "v3"

        result_mock = MagicMock()
        result_mock.fetchone.side_effect = [
            existing_version_row,       # SELECT version → v3
            _row("## Updated", "v4"),   # _get_instructions re-fetch after UPDATE
        ]
        db = MagicMock()
        db.execute.return_value = result_mock

        client = _make_client(db)
        try:
            with patch("app.routers.team_os.get_clerk_user_email", return_value="admin@example.com"):
                r = client.post(
                    "/team-os/instructions",
                    json={"content": "## Updated rules\n"},
                    headers={"x-workspace-id": WS_ID},
                )
            assert r.status_code == 200, r.text
            db.commit.assert_called_once()
            # The re-fetch row returns v4, which should appear in response
            data = r.json()
            assert data["version"] == "v4"
            assert data["content"] == "## Updated"
        finally:
            _teardown()


# ── GET /team-os/instructions/version ────────────────────────────────────────

class TestGetInstructionsVersion:
    def test_returns_version_when_row_exists(self):
        row = _version_row("v2")
        db = _db_returning(row)
        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions/version", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["version"] == "v2"
        finally:
            _teardown()

    def test_returns_v1_default_when_no_row(self):
        db = _db_returning(None)
        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions/version", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["version"] == "v1"
        finally:
            _teardown()


# ── GET /team-os/instructions/adoption ───────────────────────────────────────

class TestGetAdoption:
    def _make_adoption_row(
        self,
        email: str,
        tools: list[str],
        last_synced=None,
        instructions_version: str | None = None,
    ):
        r = MagicMock()
        r.email = email
        r.tools = tools
        r.last_synced = last_synced
        r.instructions_version = instructions_version
        return r

    def test_returns_per_member_sync_status(self):
        rows = [
            self._make_adoption_row(
                email="alice@example.com",
                tools=["claude-code", "cursor"],
                last_synced=_NOW,
                instructions_version="v3",
            ),
            self._make_adoption_row(
                email="bob@example.com",
                tools=[],
                last_synced=None,
                instructions_version=None,
            ),
        ]
        result_mock = MagicMock()
        result_mock.fetchall.return_value = rows
        db = MagicMock()
        db.execute.return_value = result_mock

        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions/adoption", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            data = r.json()
            assert len(data) == 2

            alice = next(m for m in data if m["email"] == "alice@example.com")
            assert "claude-code" in alice["tools"]
            assert "cursor" in alice["tools"]
            assert alice["version"] == "v3"
            assert alice["last_synced"] is not None

            bob = next(m for m in data if m["email"] == "bob@example.com")
            assert bob["tools"] == []
            assert bob["version"] is None
            assert bob["last_synced"] is None
        finally:
            _teardown()

    def test_returns_empty_list_when_no_members(self):
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        db = MagicMock()
        db.execute.return_value = result_mock

        client = _make_client(db)
        try:
            r = client.get("/team-os/instructions/adoption", headers={"x-workspace-id": WS_ID})
            assert r.status_code == 200, r.text
            assert r.json() == []
        finally:
            _teardown()


# ── _bump_version unit tests ──────────────────────────────────────────────────

class TestBumpVersion:
    """Direct unit tests for the version bumping helper."""

    def test_bump(self):
        from app.routers.team_os import _bump_version
        assert _bump_version("v1") == "v2"
        assert _bump_version("v3") == "v4"
        assert _bump_version("v9") == "v10"

    def test_bump_unexpected_format_returns_v2(self):
        from app.routers.team_os import _bump_version
        assert _bump_version("bad") == "v2"
        assert _bump_version("") == "v2"
        assert _bump_version(None) == "v2"
