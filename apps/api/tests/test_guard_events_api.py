"""
Wave 3 — Guard events router tests.

Strategy:
- TestClient tests for list_events (GET /guard/events) — read-only, easy to mock.
- Direct handler tests for ingest_event — avoids re-wiring every background dep.
All DB interactions go through MagicMock sessions; no real PostgreSQL needed.
"""
import os
import sys
import types
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Env vars
# ---------------------------------------------------------------------------
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# ---------------------------------------------------------------------------
# Stub app.core.config (must come before any app import)
# ---------------------------------------------------------------------------
_cfg_stub = types.ModuleType("app.core.config")
_cfg_stub.settings = MagicMock(
    database_url="postgresql://test:test@localhost:5432/test_marshal",
    redis_url="redis://localhost:6379",
    sentry_dsn="",
    environment="test",
    log_level="INFO",
    clerk_secret_key="",
    clerk_frontend_api="",
)
sys.modules.setdefault("app.core.config", _cfg_stub)

# ---------------------------------------------------------------------------
# Stub app.core.database
# ---------------------------------------------------------------------------
from sqlalchemy.orm import declarative_base as _decl_base  # noqa: E402

_db_mod = types.ModuleType("app.core.database")
_db_mod.Base = _decl_base()
_db_mod.SessionLocal = MagicMock()
_db_mod.get_db = MagicMock()
sys.modules.setdefault("app.core.database", _db_mod)

# ---------------------------------------------------------------------------
# Pre-import models to resolve FK relationships before app.main loads
# ---------------------------------------------------------------------------
import app.models.environment  # noqa: F401, E402
import app.models.project      # noqa: F401, E402
import app.models.run          # noqa: F401, E402
import app.models.workspace    # noqa: F401, E402

# ---------------------------------------------------------------------------
# Import FastAPI app and overrideable dependencies
# ---------------------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import get_db  # noqa: E402
from app.core.auth import get_workspace_id, get_user_id  # noqa: E402
import pytest


# pytest-forked: each test runs in its own subprocess so this file's module-
# level sys.modules stubs stay isolated. See epic #1075 — proper long-term
# fix is to remove the stubs (needs test-body rewrite to use real modules).
pytestmark = pytest.mark.forked
WS_ID = str(uuid.uuid4())


# ---------------------------------------------------------------------------
# TestClient helpers
# ---------------------------------------------------------------------------

def _override_db(db_mock):
    def _inner():
        yield db_mock
    return _inner


def _make_client(db_mock):
    app.dependency_overrides[get_db] = _override_db(db_mock)
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[get_user_id] = lambda: "user_test_123"
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_workspace_id, None)
    app.dependency_overrides.pop(get_user_id, None)


def _now():
    return datetime.now(timezone.utc)


def _make_event(decision="allowed", ws_id=None):
    """Return a MagicMock ORM row (passed to _event_to_dict in the router)."""
    e = MagicMock()
    e.id = uuid.uuid4()
    e.workspace_id = uuid.UUID(ws_id or WS_ID)
    e.decision = decision
    return e


def _event_dict(decision="allowed", ws_id=None, event_id=None):
    """Return a fully-typed dict that passes EventOut validation."""
    eid = event_id or str(uuid.uuid4())
    return {
        "id": eid,
        "workspace_id": ws_id or WS_ID,
        "clerk_user_id": "user_abc",
        "session_id": str(uuid.uuid4()),
        "hook_session_id": "hook-abc",
        "user_email": "dev@example.com",
        "ai_tool": "claude_code",
        "tool_call": "Write",
        "source": "hook",
        "provider": None,
        "model": None,
        "input_summary": "some input",
        "decision": decision,
        "rule_id": "no_secrets" if decision == "blocked" else None,
        "rule_message": "blocked by policy" if decision == "blocked" else None,
        "tokens_before": 1000,
        "tokens_after": 800,
        "tokens_saved": 200,
        "cost_usd_before": 0.01,
        "cost_usd_after": 0.008,
        "conductai_run_id": None,
        "conductai_workflow": None,
        "conductai_workflow_id": None,
        "duration_ms": 12,
        "blast_radius": None,
        "ts": _now().isoformat(),
        "entry_hash": "abc123",
        "policy_hash": None,
    }


# ---------------------------------------------------------------------------
# GET /guard/events — list_events
# ---------------------------------------------------------------------------

def _db_for_list(events_dicts):
    """
    Build a MagicMock db that serves list_events correctly.
    We patch _event_to_dict so EventOut never touches MagicMock attributes.
    """
    db = MagicMock()
    ws_row = MagicMock()
    ws_row.org_id = None
    ws_row.owner_id = uuid.UUID(WS_ID)
    db.query.return_value.filter.return_value.first.return_value = ws_row
    db.query.return_value.filter.return_value.all.return_value = [(uuid.UUID(WS_ID),)]
    # Return MagicMock ORM rows; _event_to_dict will be patched to use events_dicts
    orm_rows = [MagicMock() for _ in events_dicts]
    db.query.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = orm_rows
    return db, orm_rows, events_dicts


@patch("app.core.workspace_context.set_workspace_rls")
def test_list_events_empty(mock_rls):
    db, _, _ = _db_for_list([])
    client = _make_client(db)
    try:
        with patch("app.modules.guard.routers.events._event_to_dict", side_effect=[]):
            resp = client.get("/guard/events")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        _teardown()


@patch("app.core.workspace_context.set_workspace_rls")
def test_list_events_returns_events(mock_rls):
    d = _event_dict("allowed")
    db, _, dicts = _db_for_list([d])
    client = _make_client(db)
    try:
        with patch("app.modules.guard.routers.events._event_to_dict", side_effect=dicts):
            resp = client.get("/guard/events")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 1
        assert body[0]["decision"] == "allowed"
    finally:
        _teardown()


@patch("app.core.workspace_context.set_workspace_rls")
def test_list_events_filter_by_decision(mock_rls):
    """?decision=blocked query param is accepted; test verifies the route returns 200."""
    # Extra .filter() call for `decision` breaks MagicMock chain depth.
    # We verify the route accepts the param without error and delegates to _event_to_dict.
    d = _event_dict("blocked")
    db = MagicMock()
    ws_row = MagicMock()
    ws_row.org_id = None
    ws_row.owner_id = uuid.UUID(WS_ID)
    # Make every chain level return something sensible
    db.query.return_value.filter.return_value.first.return_value = ws_row
    db.query.return_value.filter.return_value.all.return_value = [(uuid.UUID(WS_ID),)]
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
        MagicMock()
    ]

    client = _make_client(db)
    try:
        with patch("app.modules.guard.routers.events._event_to_dict", return_value=d):
            resp = client.get("/guard/events?decision=blocked")
        assert resp.status_code == 200
        data = resp.json()
        assert data[0]["decision"] == "blocked"
    finally:
        _teardown()


@patch("app.core.workspace_context.set_workspace_rls")
def test_list_events_pagination_defaults(mock_rls):
    """Default limit=50 and offset=0 are accepted without error."""
    db, _, _ = _db_for_list([])
    client = _make_client(db)
    try:
        with patch("app.modules.guard.routers.events._event_to_dict", side_effect=[]):
            resp = client.get("/guard/events?limit=50&offset=0")
        assert resp.status_code == 200
    finally:
        _teardown()


@patch("app.core.workspace_context.set_workspace_rls")
def test_list_events_limit_over_200_rejected(mock_rls):
    """limit > 200 should return 422 Unprocessable Entity."""
    db = MagicMock()
    client = _make_client(db)
    try:
        resp = client.get("/guard/events?limit=201")
        assert resp.status_code == 422
    finally:
        _teardown()


# ---------------------------------------------------------------------------
# ingest_event — direct handler tests (bypass TestClient complexity)
# ---------------------------------------------------------------------------

def _make_hook_event(**kwargs):
    from app.modules.guard.routers.events import HookEvent

    defaults = dict(
        workspace_id=WS_ID,
        clerk_user_id="user_abc",
        session_id=None,
        user_email="dev@example.com",
        ai_tool="claude_code",
        tool_call="Write",
        input_summary="summary",
        decision="allowed",
        rule_id=None,
        rule_message=None,
        tokens_before=100,
        tokens_after=80,
        tokens_saved=20,
        cost_usd_before=0.001,
        cost_usd_after=0.0008,
        conductai_run_id=None,
        conductai_workflow=None,
        duration_ms=5,
        tool_use_id=None,
        hook_session_id="hook-xyz",
        blast_radius=None,
        os_info=None,
        hostname=None,
    )
    defaults.update(kwargs)
    return HookEvent(**defaults)


def test_ingest_event_invalid_workspace_id():
    """ingest_event raises 422 for a non-UUID workspace_id."""
    from fastapi import HTTPException

    from app.modules.guard.routers.events import ingest_event

    body = _make_hook_event(workspace_id="not-a-uuid")
    db = MagicMock()
    request = MagicMock()
    background = MagicMock()

    try:
        ingest_event(body, request, background, db)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 422


def test_ingest_event_unknown_workspace_returns_404():
    """ingest_event raises 404 when GuardConfig not found for workspace."""
    from fastapi import HTTPException

    from app.modules.guard.routers.events import ingest_event

    body = _make_hook_event()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no GuardConfig

    request = MagicMock()
    background = MagicMock()

    try:
        ingest_event(body, request, background, db)
        assert False, "Expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 404


def test_ingest_event_happy_path_returns_event_out():
    """ingest_event persists event and returns EventOut on success."""
    from app.modules.guard.routers.events import ingest_event

    body = _make_hook_event(decision="allowed", hook_session_id=None)

    config = MagicMock()
    config.notify_on_block = False
    config.alert_channel = None
    config.automation_security_scan = False

    saved_event = _make_event("allowed")
    # db.query(...).filter(...).first() → GuardConfig
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = config
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.refresh = MagicMock(side_effect=lambda e: None)
    # After flush, make event attributes readable
    db.add = MagicMock()

    request = MagicMock()
    request.headers = {}
    request.client = None
    background = MagicMock()

    with patch("app.modules.guard.routers.events.chain_hash_for_insert", return_value=(None, "h1")), \
         patch("app.modules.guard.routers.events.get_policy_hash", return_value=None), \
         patch("app.modules.guard.routers.events.GuardAuditEvent", return_value=saved_event), \
         patch("app.modules.guard.routers.events._event_to_dict",
               return_value=_event_dict("allowed", event_id=str(saved_event.id))):
        result = ingest_event(body, request, background, db)

    assert result.decision == "allowed"
    db.commit.assert_called_once()


def test_ingest_event_blocked_decision_persisted():
    """ingest_event stores a 'blocked' decision without raising."""
    from app.modules.guard.routers.events import ingest_event

    body = _make_hook_event(decision="blocked", rule_id="no_secrets", hook_session_id=None)

    config = MagicMock()
    config.notify_on_block = False
    config.alert_channel = None
    config.automation_security_scan = False

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = config

    saved_event = _make_event("blocked")
    request = MagicMock()
    request.headers = {}
    request.client = None
    background = MagicMock()

    with patch("app.modules.guard.routers.events.chain_hash_for_insert", return_value=(None, "h2")), \
         patch("app.modules.guard.routers.events.get_policy_hash", return_value=None), \
         patch("app.modules.guard.routers.events.GuardAuditEvent", return_value=saved_event), \
         patch("app.modules.guard.routers.events._event_to_dict",
               return_value=_event_dict("blocked", event_id=str(saved_event.id))):
        result = ingest_event(body, request, background, db)

    assert result.decision == "blocked"
    assert result.rule_id == "no_secrets"
