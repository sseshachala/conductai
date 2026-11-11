"""Unified alert registry + /guard/alerts endpoints (#2142, #2524).

Also pins Guard parity: existing Guard channel rows and the legacy
/guard/notifications surface keep their behaviour once non-guard rows exist.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://" + "test:test" + "@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

import pytest
from fastapi.testclient import TestClient

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.main import app
from app.modules.guard import notification_registry as reg
from app.modules.guard.models import GuardNotificationChannel
from app.modules.guard.routers import alerts as alerts_router
from app.modules.guard.routers.notifications import ACTIONS, resolve_channels

WS_ID = str(uuid.uuid4())


@pytest.fixture
def db():
    return MagicMock()


@pytest.fixture
def client(db):
    def _get_db():
        yield db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_workspace_id, None)


# ── Registry ────────────────────────────────────────────────────────────────

def test_registry_builtin_sources():
    types = {s.source_type for s in reg.list_sources()}
    assert {"guard", "gateway", "audit_feed", "audit_chain"} <= types
    gw = reg.get_source("gateway")
    assert gw.scoped
    assert {e.event_type for e in gw.events} == {
        "admission_refused", "spend_cap_refused", "upstream_5xx",
        "upstream_timeout", "rate_limit_exceeded",
    }
    assert all(e.supports_threshold for e in gw.events)
    assert reg.get_event("audit_chain", "verification_failed") is not None


def test_registry_guard_events_match_actions():
    assert {e.event_type for e in reg.get_source("guard").events} == set(ACTIONS)


def test_register_source_rejects_bad_severity():
    with pytest.raises(ValueError):
        reg.register_source(reg.SourceDef("x", "X", events=(reg.EventDef("e", "E", severity="loud"),)))


def test_registry_endpoint(client):
    r = client.get("/guard/alerts/registry")
    assert r.status_code == 200
    assert {s["source_type"] for s in r.json()["sources"]} >= {"gateway", "audit_feed"}


# ── Create validation ───────────────────────────────────────────────────────

def _body(**kw):
    base = {"source_type": "audit_feed", "event_type": "collector_stale",
            "channel_type": "slack", "channel_ref": "#siem"}
    base.update(kw)
    return base


def test_create_rejects_guard_source(client):
    assert client.post("/guard/alerts", json=_body(source_type="guard", event_type="block")).status_code == 422


def test_create_rejects_unknown_event(client):
    assert client.post("/guard/alerts", json=_body(event_type="nope")).status_code == 422


def test_create_rejects_threshold_on_unsupported_event(client):
    assert client.post("/guard/alerts", json=_body(threshold_per_min=5)).status_code == 422


def test_create_rejects_source_id_on_unscoped_source(client):
    assert client.post("/guard/alerts", json=_body(source_id=str(uuid.uuid4()))).status_code == 422


def test_create_rejects_private_webhook(client):
    r = client.post("/guard/alerts", json=_body(channel_type="webhook", channel_ref="https://127.0.0.1/h"))
    assert r.status_code == 422


def test_create_gateway_unknown_profile_404(client, db):
    db.query.return_value.filter.return_value.first.return_value = None
    r = client.post("/guard/alerts", json=_body(
        source_type="gateway", event_type="upstream_5xx", source_id=str(uuid.uuid4()),
        threshold_per_min=10))
    assert r.status_code == 404


def test_create_ok_stores_alert_row(client, db):
    def _refresh(row):
        row.id = uuid.uuid4()
        from datetime import datetime, timezone
        row.created_at = datetime.now(timezone.utc)

    db.refresh.side_effect = _refresh
    r = client.post("/guard/alerts", json=_body())
    assert r.status_code == 201, r.text
    row = db.add.call_args[0][0]
    assert row.action == "alert" and row.source_type == "audit_feed"
    assert row.event_type == "collector_stale"
    assert r.json()["managed_elsewhere"] is False


# ── Guard parity ────────────────────────────────────────────────────────────

def test_guard_actions_unchanged():
    assert set(ACTIONS) == {"block", "warn", "audit", "approval", "fail_open", "drift"}


def test_resolve_channels_only_guard_rows():
    db = MagicMock()
    chain = db.query.return_value
    chain.filter.return_value.all.return_value = []
    resolve_channels(db, uuid.uuid4(), "block")
    clauses = " ".join(str(c) for c in chain.filter.call_args[0])
    assert "source_type" in clauses


def test_guard_row_serializes_as_managed_elsewhere():
    from datetime import datetime, timezone
    row = GuardNotificationChannel(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), action="block", channel_type="slack",
        channel_ref="#sec", enabled=True, dedupe_window_sec=300,
        created_at=datetime.now(timezone.utc),
    )
    out = alerts_router._serialize(row)
    assert out.source_type == "guard" and out.event_type == "block" and out.managed_elsewhere


def test_model_source_type_defaults_to_guard():
    col = GuardNotificationChannel.__table__.c.source_type
    assert col.default.arg == "guard" and not col.nullable


def test_migration_check_constraint_covers_all_actions():
    src = Path(__file__).resolve().parents[2].joinpath(
        "alembic/versions/0173_guard_notif_alert_sources.py").read_text()
    m = re.search(r"action IN \(([^)]*'alert'[^)]*)\)", src)
    assert m
    listed = set(re.findall(r"'(\w+)'", m.group(1)))
    assert listed == set(ACTIONS) | {"alert"}
