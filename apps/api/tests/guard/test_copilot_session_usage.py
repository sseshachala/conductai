"""Session telemetry remains separate from tool usage and receipt accounting."""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError


def report(**overrides):
    from app.modules.guard.routers.events import SessionUsageReport
    return SessionUsageReport(**{
        "workspace_id": uuid4(), "hook_session_id": uuid4(), "snapshot_id": uuid4(),
        "observed_at": datetime.now(timezone.utc), "input_tokens": 300, "output_tokens": 20,
        **overrides,
    })


def test_maps_to_distinct_session_event_without_inventing_cost(monkeypatch):
    from app.modules.guard.routers import events_ingest as events
    body = report()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    ingest = MagicMock(return_value="recorded")
    monkeypatch.setattr(events, "ingest_event", ingest)
    auth = (str(body.workspace_id), "user")
    assert events.ingest_session_usage(body, SimpleNamespace(), BackgroundTasks(), db, auth) == "recorded"
    event = ingest.call_args.args[0]
    assert event.tool_call == "session_usage"
    assert event.ai_tool == "copilot-cli"
    assert event.tokens_before == 300 and event.tokens_after == 20
    assert event.cost_usd_after is None and event.cost_usd_before is None
    assert event.hook_session_id == str(body.hook_session_id)
    assert "not Gateway usage" in event.rule_message
    db.query.return_value.filter.return_value.with_for_update.assert_called_once()
    first_id = event.receipt_id
    events.ingest_session_usage(body, SimpleNamespace(), BackgroundTasks(), db, auth)
    assert ingest.call_args.args[0].receipt_id == first_id


def test_retried_snapshot_does_not_add_session_totals_again(monkeypatch):
    from app.modules.guard.routers import events_ingest as events
    body = report()
    db = MagicMock()
    existing = object()
    db.query.return_value.filter.return_value.first.return_value = existing
    monkeypatch.setattr(events, "_event_to_dict", lambda row: {"row": row})
    monkeypatch.setattr(events, "EventOut", lambda **values: values)
    ingest = MagicMock()
    monkeypatch.setattr(events, "ingest_event", ingest)
    result = events.ingest_session_usage(body, SimpleNamespace(), BackgroundTasks(), db,
                                        (str(body.workspace_id), "user"))
    assert result == {"row": existing}
    ingest.assert_not_called()


def test_workspace_mismatch_rejected_before_database_access():
    from app.modules.guard.routers import events_ingest as events
    db = MagicMock()
    with pytest.raises(HTTPException) as error:
        events.ingest_session_usage(report(), SimpleNamespace(), BackgroundTasks(), db, (str(uuid4()), "user"))
    assert error.value.status_code == 403
    db.query.assert_not_called()


@pytest.mark.parametrize("tokens", [-1, True, 1.5, 2**31])
def test_invalid_token_counts_rejected(tokens):
    with pytest.raises(ValidationError):
        report(input_tokens=tokens)


def test_naive_time_rejected():
    from app.modules.guard.routers import events_ingest as events
    body = report(observed_at=datetime(2026, 9, 28))
    with pytest.raises(HTTPException) as error:
        events.ingest_session_usage(body, SimpleNamespace(), BackgroundTasks(), MagicMock(),
                                    (str(body.workspace_id), "user"))
    assert error.value.status_code == 422


@pytest.mark.parametrize("surface", ["codex", "codex-cli", "codex-desktop", "claude-code", "copilot-cli"])
def test_all_supported_clients_map_to_session_usage(monkeypatch, surface):
    from app.modules.guard.routers import events_ingest as events
    body = report(ai_tool=surface)
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    ingest = MagicMock()
    monkeypatch.setattr(events, "ingest_event", ingest)
    events.ingest_session_usage(body, SimpleNamespace(), BackgroundTasks(), db, (str(body.workspace_id), "user"))
    event = ingest.call_args.args[0]
    assert event.ai_tool == surface and event.tool_call == "session_usage"
    assert event.tokens_before == 300 and event.tokens_after == 20
    assert event.cost_usd_before is None and event.cost_usd_after is None


def test_unsupported_usage_client_rejected():
    with pytest.raises(ValidationError):
        report(ai_tool="gateway")


def test_metadata_only_backfill_does_not_invent_zero_usage():
    from app.modules.guard.routers import events_ingest as events
    body = events.UsageUpdate(workspace_id=str(uuid4()), hook_session_id="session", tool_use_id="call-id", execution_status="success")
    event = SimpleNamespace(decision="warned")
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.filter.return_value = q
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = event
    assert events.update_usage(body, db, (body.workspace_id, "user")).updated
    assert event.tokens_before is None and event.tokens_after is None
    assert event.cost_usd_before is None and event.cost_usd_after is None
    assert event.execution_status == "success"


def test_legacy_backfill_still_accepts_reported_tokens():
    from app.modules.guard.routers import events_ingest as events
    body = events.UsageUpdate(workspace_id=str(uuid4()), hook_session_id="session", tokens_input=100, tokens_output=20)
    event = SimpleNamespace(decision="allowed")
    db = MagicMock()
    q = db.query.return_value.filter.return_value
    q.filter.return_value = q
    db.query.return_value.filter.return_value.order_by.return_value.first.return_value = event
    events.update_usage(body, db, (body.workspace_id, "user"))
    assert (event.tokens_before, event.tokens_after) == (100, 20)
