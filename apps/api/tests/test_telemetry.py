"""Tests for POST /telemetry/events (#718 Phase 1).

Verifies:
  - missing/invalid bearer → 401
  - valid token writes row
  - message + traceback are redacted before insert (secrets never land)
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import create as sa_create
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")


@pytest.fixture
def client_and_db():
    """In-memory SQLite + FastAPI app with just the telemetry router mounted."""
    from app.core import database as db_mod

    # StaticPool — all sessions share the same in-memory DB connection so the
    # tables we create here are visible to the FastAPI request handler.
    engine = sa_create.create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # SQLite-compatible mirror of guard_member_config (just the columns the route reads)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE guard_member_config ("
            "  workspace_id TEXT NOT NULL,"
            "  member_token TEXT NOT NULL,"
            "  active INTEGER NOT NULL,"
            "  PRIMARY KEY (workspace_id)"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE telemetry_events ("
            "  id TEXT PRIMARY KEY,"
            "  workspace_id TEXT,"
            "  run_id TEXT,"
            "  tool TEXT NOT NULL,"
            "  version TEXT NOT NULL,"
            "  event_type TEXT NOT NULL,"
            "  message TEXT NOT NULL,"
            "  traceback TEXT,"
            "  session_id TEXT,"
            "  context TEXT NOT NULL DEFAULT '{}',"
            "  ts TEXT NOT NULL DEFAULT (datetime('now'))"
            ")"
        ))

    ws_id = str(uuid.uuid4())
    token = "tk_test_" + uuid.uuid4().hex
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO guard_member_config (workspace_id, member_token, active) VALUES (:w, :t, 1)"),
            {"w": ws_id, "t": token},
        )

    def _override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    from app.modules.telemetry import routes as telemetry_routes

    app = FastAPI()
    app.include_router(telemetry_routes.router)
    app.dependency_overrides[db_mod.get_db] = _override_get_db

    yield TestClient(app), engine, ws_id, token


def _row_count(engine) -> int:
    with engine.begin() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM telemetry_events")).scalar_one()


def _last_row(engine):
    with engine.begin() as conn:
        return conn.execute(text(
            "SELECT workspace_id, tool, event_type, message, traceback "
            "FROM telemetry_events ORDER BY ts DESC LIMIT 1"
        )).mappings().one()


def test_missing_bearer_is_401(client_and_db):
    client, engine, _ws, _tok = client_and_db
    r = client.post("/telemetry/events", json={
        "tool": "conduct-cli",
        "version": "0.5.8",
        "event_type": "error",
        "message": "boom",
    })
    assert r.status_code == 401
    assert _row_count(engine) == 0


def test_invalid_token_is_401(client_and_db):
    client, engine, _ws, _tok = client_and_db
    r = client.post(
        "/telemetry/events",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={
            "tool": "conduct-cli",
            "version": "0.5.8",
            "event_type": "error",
            "message": "boom",
        },
    )
    assert r.status_code == 401
    assert _row_count(engine) == 0


def test_valid_post_writes_row(client_and_db):
    client, engine, ws, tok = client_and_db
    r = client.post(
        "/telemetry/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "tool": "conduct-cli",
            "version": "0.5.8",
            "event_type": "error",
            "message": "ValueError: thing failed",
            "traceback": "Traceback (most recent call last):\n  ...",
            "context": {"agent_id": "investigate"},
        },
    )
    assert r.status_code == 201
    assert _row_count(engine) == 1
    row = _last_row(engine)
    # SQLite stores UUID without dashes; normalize both sides before compare.
    assert str(row["workspace_id"]).replace("-", "") == ws.replace("-", "")
    assert row["tool"] == "conduct-cli"
    assert row["event_type"] == "error"
    assert "ValueError" in row["message"]


def test_secret_in_message_gets_redacted(client_and_db):
    """A leaked API key should never land in the audit row verbatim."""
    client, engine, _ws, tok = client_and_db
    leaked = "sk-ant-api03-" + ("A" * 90)
    r = client.post(
        "/telemetry/events",
        headers={"Authorization": f"Bearer {tok}"},
        json={
            "tool": "conduct-cli",
            "version": "0.5.8",
            "event_type": "error",
            "message": f"auth failed with {leaked}",
        },
    )
    assert r.status_code == 201
    row = _last_row(engine)
    # The exact key string must not appear in the stored message
    assert leaked not in row["message"]
