"""Verify GET /glens/sessions/{id}/stream — auth, response type, replay wrapper.

Focus: the auth boundary + SSE response shape. The pub/sub read loop
requires a live Redis; we do NOT exercise it here — PR 3 wires actor
endpoints as publishers and covers the round-trip in an integration
test if we ever add one. Env vars come from tests/conftest.py.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import app.models.run          # noqa: F401
import app.models.workspace    # noqa: F401

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.main import app
from app.modules.glens.routers.session_stream import _sse_frame


WS_ID = str(uuid.uuid4())
SESSION_ID = str(uuid.uuid4())


def _make_client(session_lookup_ok: bool = True):
    def _noop_permission(perm):
        async def _check():
            return "admin"
        return _check

    if session_lookup_ok:
        def _stub_session(db, session_id, ws_uuid):
            s = MagicMock()
            s.id = uuid.UUID(session_id)
            s.workspace_id = ws_uuid
            return s
    else:
        def _stub_session(db, session_id, ws_uuid):
            raise HTTPException(status_code=404, detail="Session not found")

    app.dependency_overrides[get_db] = lambda: iter([MagicMock()])
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[require_permission] = _noop_permission
    import app.modules.glens.routers.session_stream as mod
    mod._get_session = _stub_session
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.clear()
    import app.modules.glens.routers.session_stream as mod
    from app.modules.glens.routers._helpers import _get_session as real
    mod._get_session = real


def test_returns_404_when_session_not_in_workspace() -> None:
    client = _make_client(session_lookup_ok=False)
    try:
        resp = client.get(f"/glens/sessions/{SESSION_ID}/stream")
        assert resp.status_code == 404
    finally:
        _teardown()


def test_sse_frame_includes_id_line_when_entry_id_present() -> None:
    frame = _sse_frame("1699999999999-0", '{"foo":"bar"}')
    assert frame.startswith("id: 1699999999999-0\n")
    assert 'data: {"foo":"bar"}' in frame
    assert frame.endswith("\n\n")


def test_sse_frame_omits_id_line_when_entry_id_blank() -> None:
    frame = _sse_frame("", '{"foo":"bar"}')
    assert not frame.startswith("id:")
    assert frame == 'data: {"foo":"bar"}\n\n'


def test_endpoint_is_registered_on_app() -> None:
    """FastAPI does not always expose sub-router routes via app.routes at
    the top level; the openapi schema is the authoritative source."""
    schema = app.openapi()
    assert "/glens/sessions/{session_id}/stream" in schema["paths"]
    assert "get" in schema["paths"]["/glens/sessions/{session_id}/stream"]
