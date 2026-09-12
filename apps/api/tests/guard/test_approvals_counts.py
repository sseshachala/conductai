"""GET /guard/approvals returns workspace-wide status counts alongside the
filtered items list (#1887).

Regression: pre-#1887, the frontend derived counts from the filtered
`items` array, so every inactive status showed 0. The endpoint now
returns a `counts` object with the true per-status totals independent
of the client's `status` filter.
"""
import os
import uuid
from unittest.mock import MagicMock

# Env stubs so `from app.main import app` doesn't complain.
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
from app.core.auth import get_workspace_id, require_permission

WS_ID = str(uuid.uuid4())


def _make_client(db_mock):
    def _noop_permission(_perm):
        async def _check():
            return "admin"
        return _check

    def _get_db():
        yield db_mock

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[require_permission] = _noop_permission
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_workspace_id, None)
    app.dependency_overrides.pop(require_permission, None)


def test_list_returns_status_counts_alongside_filtered_items():
    """The counts object must reflect workspace-wide totals — not the
    filtered `items` set. Simulate: the user asks for status=rejected;
    the query for items returns []; but the count query independently
    returns the true breakdown (3 pending, 12 approved, 5 rejected,
    1 timed_out)."""
    db = MagicMock()

    # First query: the filtered items list — return empty since user
    # asked for status=rejected but the mock doesn't populate rows.
    items_q = db.query.return_value.filter.return_value.filter.return_value
    items_q.order_by.return_value.limit.return_value.all.return_value = []

    # Second query: the workspace-wide GROUP BY count query. Returns
    # (status, count) tuples.
    count_rows = [
        ("pending", 3),
        ("approved", 12),
        ("rejected", 5),
        ("timed_out", 1),
    ]

    def _query_side_effect(*args):
        # The count query passes two args (status column + func.count).
        # The items query passes GuardApprovalRequest as the only arg.
        # Route by argcount so both branches work.
        if len(args) == 2:
            m = MagicMock()
            m.filter.return_value.group_by.return_value.all.return_value = count_rows
            return m
        return db.query.return_value

    db.query.side_effect = _query_side_effect

    client = _make_client(db)
    try:
        res = client.get("/guard/approvals?status=rejected")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["items"] == []
        assert body["counts"] == {
            "pending": 3,
            "approved": 12,
            "rejected": 5,
            "timed_out": 1,
        }
    finally:
        _teardown()


def test_list_returns_zero_counts_when_workspace_empty():
    """No rows in guard_approval_requests → all counts are 0."""
    db = MagicMock()

    items_q = db.query.return_value.filter.return_value.filter.return_value
    items_q.order_by.return_value.limit.return_value.all.return_value = []

    def _query_side_effect(*args):
        if len(args) == 2:
            m = MagicMock()
            m.filter.return_value.group_by.return_value.all.return_value = []
            return m
        return db.query.return_value

    db.query.side_effect = _query_side_effect

    client = _make_client(db)
    try:
        res = client.get("/guard/approvals?status=pending")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["counts"] == {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "timed_out": 0,
        }
    finally:
        _teardown()
