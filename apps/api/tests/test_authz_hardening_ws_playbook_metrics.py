"""Workspace binding on the policy websocket, submitter workspace resolution,
and constant-time metrics token handling."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.modules.guard.routers import ws as ws_mod
from app.routers import playbooks as pb_mod

WS_A = str(uuid.uuid4())
WS_B = str(uuid.uuid4())


# ── websocket ────────────────────────────────────────────────────────────────

@pytest.fixture
def ws_client(monkeypatch):
    monkeypatch.setattr(ws_mod, "_token_workspace", lambda t: WS_A if t == "tok-a" else None)
    pubsub = MagicMock()
    pubsub.get_message.return_value = {"type": "message", "data": '{"type":"policy_invalidated"}'}
    redis = MagicMock()
    redis.pubsub.return_value = pubsub
    monkeypatch.setattr(ws_mod, "_r", lambda: redis)
    return TestClient(app)


def test_ws_token_for_other_workspace_rejected(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"/guard/ws/policy?workspace_id={WS_B}&token=tok-a"):
            pass


def test_ws_invalid_token_rejected(ws_client):
    with pytest.raises(WebSocketDisconnect):
        with ws_client.websocket_connect(f"/guard/ws/policy?workspace_id={WS_A}&token=bad"):
            pass


def test_ws_same_workspace_accepted(ws_client):
    with ws_client.websocket_connect(f"/guard/ws/policy?workspace_id={WS_A}&token=tok-a") as ws:
        assert "policy_invalidated" in ws.receive_text()


# ── playbook submit ──────────────────────────────────────────────────────────

class _Db:
    def __init__(self, member: bool):
        self.member = member
        self.added = []

    def execute(self, *a, **k):
        r = MagicMock()
        r.fetchone.return_value = (1,) if self.member else None
        return r

    def add(self, row):
        self.added.append(row)

    def commit(self):
        pass

    def refresh(self, row):
        row.id = uuid.uuid4()


@pytest.fixture
def submit(monkeypatch):
    import app.core.auth as auth_mod
    import app.dsl.loader as loader

    monkeypatch.setattr(auth_mod, "_clerk_enabled", lambda: True)
    monkeypatch.setattr(
        auth_mod, "_verify_clerk_token",
        lambda t: {"sub": "user_1", "org_id": "org-claim"} if t == "good" else None,
    )
    monkeypatch.setattr(loader, "load_workflow_yaml", lambda *a, **k: MagicMock(name="wf"))

    async def _ok(_t):
        return True

    monkeypatch.setattr(pb_mod, "_verify_recaptcha", _ok)
    monkeypatch.setattr(pb_mod, "PlaybookSubmission", lambda **kw: MagicMock(**kw))

    def go(member, headers, body_extra=None):
        db = _Db(member)
        app.dependency_overrides[get_db] = lambda: db
        try:
            body = {"yaml_content": "name: x", **(body_extra or {})}
            resp = TestClient(app, raise_server_exceptions=False).post(
                "/playbooks/submit", json=body, headers=headers
            )
        finally:
            app.dependency_overrides.pop(get_db, None)
        return resp, db

    return go


def test_submit_non_member_header_rejected(submit):
    resp, db = submit(False, {"Authorization": "Bearer good", "X-Workspace-Id": WS_B})
    assert resp.status_code == 403
    assert db.added == []


def test_submit_member_header_honoured(submit):
    resp, db = submit(True, {"Authorization": "Bearer good", "X-Workspace-Id": WS_B})
    assert db.added[0].submitter_workspace_id == WS_B


def test_submit_authenticated_without_header_uses_org(submit):
    resp, db = submit(False, {"Authorization": "Bearer good"})
    assert db.added[0].submitter_workspace_id == "org-claim"


def test_submit_anonymous_ignores_header(submit):
    resp, db = submit(True, {"X-Workspace-Id": WS_B}, {"recaptcha_token": "r"})
    assert db.added[0].submitter_workspace_id is None


# ── metrics token ────────────────────────────────────────────────────────────

@pytest.fixture
def prod_metrics(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "metrics_token", "s3cret")
    return TestClient(app)


@pytest.mark.parametrize("path", ["/metrics", "/admin/cache-stats"])
def test_metrics_token(prod_metrics, path):
    assert prod_metrics.get(path, headers={"X-Metrics-Token": "s3cret"}).status_code == 200
    assert prod_metrics.get(path, headers={"X-Metrics-Token": "wrong"}).status_code == 401
    assert prod_metrics.get(path).status_code == 401


def test_metrics_empty_configured_token_refuses(monkeypatch):
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "metrics_token", "")
    c = TestClient(app)
    assert c.get("/metrics").status_code == 401
    assert c.get("/metrics", headers={"X-Metrics-Token": ""}).status_code == 401
