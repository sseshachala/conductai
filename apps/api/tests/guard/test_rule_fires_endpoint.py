"""#1755 Slice 2 — GET /guard/events/rule/{rule_id}/fires.

Property 9: raw input_summary must never leave the API. The redacted
projection replaces secrets in-place and adds hash + size fields for
dedupe/volume signals without exposing payload.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_workspace_id, get_user_id

    db_mock = MagicMock()
    app.dependency_overrides[get_db] = lambda: db_mock
    app.dependency_overrides[get_workspace_id] = lambda: "00000000-0000-0000-0000-0000000000ab"
    app.dependency_overrides[get_user_id] = lambda: "user_test"
    return db_mock, TestClient(app, raise_server_exceptions=False)


def _clear():
    from app.main import app
    app.dependency_overrides.clear()


def _event(ts_iso: str, rule_id: str, input_summary: str) -> MagicMock:
    e = MagicMock()
    e.id = "abcd-1234"
    e.ts = MagicMock(isoformat=lambda: ts_iso)
    e.rule_id = rule_id
    e.decision = "blocked"
    e.tool_call = "write_file"
    e.source = "hook"
    e.ai_tool = "claude-code"
    e.input_summary = input_summary
    return e


def _install_rows(db: MagicMock, rows: list):
    """Stub the ORM query chain for the endpoint's read."""
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    db.query.return_value = q


def test_endpoint_redacts_input_summary_before_returning():
    db, client = _client()
    secret = "sk" + "-" + ("X" * 30)
    _install_rows(db, [_event("2026-09-10T00:00:00Z", "hipaa-x", f"leak: {secret}")])
    try:
        with patch(
            "app.modules.guard.routers.events._org_ws_subquery",
            return_value=MagicMock(),
        ):
            r = client.get("/guard/events/rule/hipaa-x/fires")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body) == 1
        row = body[0]
        # Property 9: raw secret must not surface.
        assert secret not in row["input_summary_redacted"], (
            "raw secret leaked into rule-fires response"
        )
        # Redacted marker present so caller sees SOMETHING happened.
        assert "REDACTED" in row["input_summary_redacted"].upper()
    finally:
        _clear()


def test_endpoint_hash_prefix_and_size_fields_populated():
    db, client = _client()
    raw = "hello world"
    _install_rows(db, [_event("2026-09-10T00:00:00Z", "rule-A", raw)])
    try:
        with patch(
            "app.modules.guard.routers.events._org_ws_subquery",
            return_value=MagicMock(),
        ):
            r = client.get("/guard/events/rule/rule-A/fires")
        assert r.status_code == 200
        row = r.json()[0]
        assert row["input_size_bytes"] == len(raw.encode("utf-8"))
        assert row["input_hash_prefix"] is not None
        # sha256("hello world") == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
        assert row["input_hash_prefix"] == "b94d27b9934d3e08"
    finally:
        _clear()


def test_endpoint_empty_result_returns_empty_list():
    db, client = _client()
    _install_rows(db, [])
    try:
        with patch(
            "app.modules.guard.routers.events._org_ws_subquery",
            return_value=MagicMock(),
        ):
            r = client.get("/guard/events/rule/nobody-fired-this/fires")
        assert r.status_code == 200
        assert r.json() == []
    finally:
        _clear()


def test_endpoint_null_input_summary_yields_null_preview():
    """When a row has no input_summary at all (e.g. approval-flow rows),
    the endpoint returns null preview + zero size, not an error."""
    db, client = _client()
    _install_rows(db, [_event("2026-09-10T00:00:00Z", "rule-x", "")])
    try:
        with patch(
            "app.modules.guard.routers.events._org_ws_subquery",
            return_value=MagicMock(),
        ):
            r = client.get("/guard/events/rule/rule-x/fires")
        assert r.status_code == 200
        row = r.json()[0]
        assert row["input_summary_redacted"] is None
        assert row["input_hash_prefix"] is None
        assert row["input_size_bytes"] == 0
    finally:
        _clear()
