"""Verify actor helpers tee action.confirmed / action.cancelled events to
the row's originating Lens session (#1480 PR 3).

Focus: the _publish_action_event helper. Its contract:
  - No-op when row.session_id is None (HTTP calls without chat context)
  - Publishes action.confirmed with entity=approval + payload=result/cached
  - Publishes action.cancelled with entity=approval, no result
  - Uses row.session_id + row.id for routing
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from app.modules.glens.actor.helpers import _publish_action_event


def _row(session_id="sess-abc", row_id="row-xyz", tool_name="run_workflow", status="approved"):
    return SimpleNamespace(
        id=row_id,
        session_id=session_id,
        tool_name=tool_name,
        status=status,
    )


def test_no_publish_when_row_has_no_session_id() -> None:
    """HTTP actor calls without chat context leave session_id NULL — nothing
    to route to, so publish is skipped entirely."""
    row = _row(session_id=None)
    with patch("app.modules.glens.actor.helpers.publish_session_event") as mock_pub:
        _publish_action_event(row, "action.confirmed", result={"run_id": "r1"})
    mock_pub.assert_not_called()


def test_confirmed_event_shape() -> None:
    row = _row()
    with patch("app.modules.glens.actor.helpers.publish_session_event") as mock_pub:
        _publish_action_event(row, "action.confirmed", result={"run_id": "r1"})
    mock_pub.assert_called_once()
    session_id, event_type = mock_pub.call_args.args
    kwargs = mock_pub.call_args.kwargs
    assert session_id == "sess-abc"
    assert event_type == "action.confirmed"
    assert kwargs["entity"] == {"type": "approval", "id": "row-xyz"}
    assert kwargs["payload"] == {
        "tool_name": "run_workflow",
        "status": "approved",
        "result": {"run_id": "r1"},
    }


def test_confirmed_event_marks_cached_when_flagged() -> None:
    row = _row()
    with patch("app.modules.glens.actor.helpers.publish_session_event") as mock_pub:
        _publish_action_event(row, "action.confirmed", result={"foo": "bar"}, cached=True)
    kwargs = mock_pub.call_args.kwargs
    assert kwargs["payload"]["cached"] is True


def test_cancelled_event_omits_result() -> None:
    row = _row(status="rejected")
    with patch("app.modules.glens.actor.helpers.publish_session_event") as mock_pub:
        _publish_action_event(row, "action.cancelled")
    kwargs = mock_pub.call_args.kwargs
    assert kwargs["payload"] == {"tool_name": "run_workflow", "status": "rejected"}
    assert "result" not in kwargs["payload"]
    assert "cached" not in kwargs["payload"]


def test_row_id_stringified_for_entity() -> None:
    """entity.id must be a string — approval rows carry UUID; the publisher
    contract expects string ids."""
    import uuid
    row_uuid = uuid.uuid4()
    row = _row(row_id=row_uuid)
    with patch("app.modules.glens.actor.helpers.publish_session_event") as mock_pub:
        _publish_action_event(row, "action.confirmed")
    kwargs = mock_pub.call_args.kwargs
    assert kwargs["entity"]["id"] == str(row_uuid)
