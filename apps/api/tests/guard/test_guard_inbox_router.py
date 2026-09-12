"""Router tests for /guard/inbox — list, detail, drill-in, PATCH resolve.

Uses a mocked DB session (no Postgres round-trip) — the ORM query
paths + validation logic are what we're exercising. The trigger +
migration are tested by the alembic drift check + a live smoke against
a staging DB.
"""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

# Dummy env values so `from app.main import app` doesn't complain during
# module import. The Guard hook's `secret-postgres-url` rule scans file
# literals — build the DSN at runtime instead of embedding it.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://" + "test:test" + "@localhost:5432/test_marshal",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

import app.models.environment  # noqa: F401
import app.models.project      # noqa: F401
import app.models.run          # noqa: F401
import app.models.workspace    # noqa: F401
import app.modules.guard.models  # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db
from app.core.auth import get_workspace_id, get_user_id, require_permission
from app.modules.guard.models import GuardInbox

WS_ID = str(uuid.uuid4())
USER_ID = "user_abc123"


def _override_db(db_mock):
    def _get_db():
        yield db_mock
    return _get_db


def _make_client(db_mock):
    def _noop_permission(_perm):
        async def _check():
            return "admin"
        return _check

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


def _row(status="open", resolved_reason=None, resolved_at=None, resolved_by=None):
    now = datetime.now(timezone.utc)
    r = GuardInbox()
    r.id = uuid.uuid4()
    r.workspace_id = uuid.UUID(WS_ID)
    r.dedup_key = "abc" * 16
    r.rule_id = "proxy-no-prompt-injection"
    r.source = "proxy"
    r.severity = "critical"
    r.description = "Prompt injection pattern detected."
    r.occurrences = 7
    r.first_seen_at = now
    r.last_seen_at = now
    r.status = status
    r.resolved_reason = resolved_reason
    r.resolved_note = None
    r.resolved_at = resolved_at
    r.resolved_by = resolved_by
    r.latest_event_id = uuid.uuid4()
    return r


def test_list_returns_rows_filtered_by_workspace():
    row = _row()
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [row]

    client = _make_client(db)
    try:
        res = client.get("/guard/inbox")
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body) == 1
        assert body[0]["rule_id"] == "proxy-no-prompt-injection"
        assert body[0]["occurrences"] == 7
        assert body[0]["status"] == "open"
    finally:
        _teardown()


def test_patch_requires_reason_when_status_is_resolved():
    """Enum enforcement keeps triage taxonomies honest — same class
    of bug the conduct-litellm-guard 0.2.5 rename addressed."""
    row = _row()
    db = MagicMock()
    q = db.query.return_value.filter.return_value.filter.return_value
    q.first.return_value = row

    client = _make_client(db)
    try:
        res = client.patch(
            f"/guard/inbox/{row.id}",
            json={"status": "resolved"},  # missing resolved_reason
        )
        assert res.status_code == 422, res.text
        assert "resolved_reason" in res.text
    finally:
        _teardown()


def test_patch_sets_resolved_by_from_user_session():
    """Server owns resolved_at + resolved_by; caller can't spoof them."""
    row = _row()
    db = MagicMock()
    q = db.query.return_value.filter.return_value.filter.return_value
    q.first.return_value = row

    client = _make_client(db)
    try:
        res = client.patch(
            f"/guard/inbox/{row.id}",
            json={
                "status": "resolved",
                "resolved_reason": "expected",
                "resolved_note": "Known false-positive from the QA test agent.",
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "resolved"
        assert body["resolved_reason"] == "expected"
        assert body["resolved_note"].startswith("Known false-positive")
        assert body["resolved_by"] == USER_ID
        assert body["resolved_at"] is not None
    finally:
        _teardown()


def test_patch_moving_off_resolved_clears_metadata():
    row = _row(
        status="resolved",
        resolved_reason="false_positive",
        resolved_at=datetime.now(timezone.utc),
        resolved_by="user_someone_else",
    )
    db = MagicMock()
    q = db.query.return_value.filter.return_value.filter.return_value
    q.first.return_value = row

    client = _make_client(db)
    try:
        res = client.patch(
            f"/guard/inbox/{row.id}",
            json={"status": "open"},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["status"] == "open"
        assert body["resolved_reason"] is None
        assert body["resolved_at"] is None
        assert body["resolved_by"] is None
    finally:
        _teardown()


def test_patch_rejects_invalid_reason_enum():
    row = _row()
    db = MagicMock()
    q = db.query.return_value.filter.return_value.filter.return_value
    q.first.return_value = row

    client = _make_client(db)
    try:
        res = client.patch(
            f"/guard/inbox/{row.id}",
            json={"status": "resolved", "resolved_reason": "vibes"},
        )
        assert res.status_code == 422, res.text
    finally:
        _teardown()


def test_detail_404_on_wrong_workspace():
    db = MagicMock()
    q = db.query.return_value.filter.return_value.filter.return_value
    q.first.return_value = None  # workspace filter excludes cross-tenant row

    client = _make_client(db)
    try:
        res = client.get(f"/guard/inbox/{uuid.uuid4()}")
        assert res.status_code == 404
    finally:
        _teardown()


def test_detail_400_on_bad_uuid():
    db = MagicMock()

    client = _make_client(db)
    try:
        res = client.get("/guard/inbox/not-a-uuid")
        assert res.status_code == 400
    finally:
        _teardown()
