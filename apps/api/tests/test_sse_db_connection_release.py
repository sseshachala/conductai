"""Long-lived SSE endpoints must not hold a pooled DB connection for the stream.

A Depends(get_db) session stays checked out until the response finishes, so
each open /guard/events/stream tab pinned one connection for 5 minutes and
~15 tabs exhausted the pool (production 502s, 2026-11-24).
"""
from __future__ import annotations

import asyncio
import inspect

from app.modules.guard.routers import events_query


def test_events_stream_takes_no_request_scoped_session():
    assert "db" not in inspect.signature(events_query.stream_events).parameters


def test_events_stream_authorizes_off_loop_and_closes_its_session(monkeypatch):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    monkeypatch.setattr(events_query, "SessionLocal", FakeSession)
    monkeypatch.setattr(events_query, "stream_credentials", lambda request: None)
    monkeypatch.setattr(events_query, "get_workspace_id", lambda **kw: kw["ws_id"])

    assert events_query._authorize_stream(object(), "ws-1") == "ws-1"
    assert closed == [True]


def test_events_stream_closes_session_when_auth_fails(monkeypatch):
    closed = []

    class FakeSession:
        def close(self):
            closed.append(True)

    def deny(**kw):
        raise PermissionError("denied")

    monkeypatch.setattr(events_query, "SessionLocal", FakeSession)
    monkeypatch.setattr(events_query, "stream_credentials", lambda request: None)
    monkeypatch.setattr(events_query, "get_workspace_id", deny)

    try:
        events_query._authorize_stream(object(), "ws-1")
    except PermissionError:
        pass
    assert closed == [True]
