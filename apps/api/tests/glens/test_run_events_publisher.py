"""Verify publish_run_status tees run.status_changed to the run's session
channel — foundation for the <RunBubble> live status (#1480 PR 5).

Contract:
- No-op when run.session_id is None (non-Lens-originated runs)
- Publishes entity=run + payload={status} on happy path
- Includes error when passed
- session_id and run.id stringified for the publisher
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.modules.glens.run_events import publish_run_status


def _run(session_id="sess-abc", run_id="run-xyz", status="running"):
    return SimpleNamespace(id=run_id, session_id=session_id, status=status)


def test_no_publish_when_run_has_no_session_id() -> None:
    """Runs from workflow UI / CLI / webhooks leave session_id NULL and
    must not touch the session channel — nothing to route to."""
    run = _run(session_id=None)
    with patch("app.modules.glens.run_events.publish_session_event") as mock_pub:
        publish_run_status(run)
    mock_pub.assert_not_called()


def test_publishes_run_status_changed_with_entity_and_status() -> None:
    run = _run(status="running")
    with patch("app.modules.glens.run_events.publish_session_event") as mock_pub:
        publish_run_status(run)
    session_id, event_type = mock_pub.call_args.args
    kwargs = mock_pub.call_args.kwargs
    assert session_id == "sess-abc"
    assert event_type == "run.status_changed"
    assert kwargs["entity"] == {"type": "run", "id": "run-xyz"}
    assert kwargs["payload"] == {"status": "running"}


def test_error_included_when_provided() -> None:
    run = _run(status="failed")
    with patch("app.modules.glens.run_events.publish_session_event") as mock_pub:
        publish_run_status(run, error="boom")
    assert mock_pub.call_args.kwargs["payload"] == {"status": "failed", "error": "boom"}


def test_uuid_ids_stringified() -> None:
    import uuid
    session_uuid = uuid.uuid4()
    run_uuid = uuid.uuid4()
    run = _run(session_id=session_uuid, run_id=run_uuid)
    with patch("app.modules.glens.run_events.publish_session_event") as mock_pub:
        publish_run_status(run)
    session_id, _ = mock_pub.call_args.args
    kwargs = mock_pub.call_args.kwargs
    assert session_id == str(session_uuid)
    assert kwargs["entity"]["id"] == str(run_uuid)


def test_no_publish_when_session_id_attr_missing() -> None:
    """Defensive: SimpleNamespace without session_id at all — getattr default
    catches this. Real Run rows always have the column post-PR-1 but tests
    with dummy objects should still be safe."""
    run = SimpleNamespace(id="r1", status="running")  # no session_id attr
    with patch("app.modules.glens.run_events.publish_session_event") as mock_pub:
        publish_run_status(run)
    mock_pub.assert_not_called()
