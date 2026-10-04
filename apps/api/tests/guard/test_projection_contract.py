import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.modules.guard.projection_contract import (
    ProjectionMessage,
    ProjectionSourceKind,
)
from app.modules.guard.projection_policy import (
    audit_event_projection_reason,
    audit_event_source_version,
    normalize_projection_decision,
    projection_expires_at,
    projection_is_expired,
)


def test_projection_message_validates_and_round_trips_compact_json():
    message = ProjectionMessage(
        intent_id=str(uuid4()),
        workspace_id=str(uuid4()),
        source_kind="audit_event",
        source_id="event-123",
        source_version="hash-456",
    )

    encoded = message.to_json()

    assert encoded == json.dumps(
        message.to_dict(), sort_keys=True, separators=(",", ":")
    )
    assert ProjectionMessage.from_json(encoded) == message
    assert set(json.loads(encoded)) == {
        "intent_id",
        "workspace_id",
        "source_kind",
        "source_id",
        "source_version",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("intent_id", "not-a-uuid"),
        ("workspace_id", ""),
        ("source_kind", "prompt"),
        ("source_id", "  "),
        ("source_version", ""),
    ],
)
def test_projection_message_rejects_invalid_fields(field, value):
    values = {
        "intent_id": str(uuid4()),
        "workspace_id": str(uuid4()),
        "source_kind": ProjectionSourceKind.RULE,
        "source_id": "rule-1",
        "source_version": "v1",
    }
    values[field] = value

    with pytest.raises(ValueError):
        ProjectionMessage(**values)


@pytest.mark.parametrize(
    ("producer_value", "normalized"),
    [
        ("allow", "allowed"),
        ("audited", "allowed"),
        ("permitted", "allowed"),
        ("block", "blocked"),
        ("deny", "blocked"),
        ("warn", "warned"),
        ("warning", "warned"),
        ("approval", "approval"),
        ("requires-approval", "approval"),
        ("approval_required", "approval"),
    ],
)
def test_decision_spelling_table(producer_value, normalized):
    assert normalize_projection_decision(producer_value) == normalized


@pytest.mark.parametrize("severity", ["high", "HIGH", "critical", "Critical"])
def test_high_and_critical_rules_are_security_relevant(severity):
    rules = [{"severity": severity, "action": "allow"}]

    assert audit_event_projection_reason("allowed", rules) == "security_relevant"


@pytest.mark.parametrize("action", ["block", "warning", "requires_approval"])
def test_enforcement_rule_actions_are_security_relevant(action):
    rules = [{"severity": "low", "action": action}]

    assert audit_event_projection_reason("allowed", rules) == "security_relevant"


def test_routine_allowed_event_is_skipped():
    rules = [{"severity": "low", "action": "allow"}]

    assert audit_event_projection_reason("allowed", rules) is None


@pytest.mark.parametrize(
    "source_kind",
    [ProjectionSourceKind.RULE, ProjectionSourceKind.DISCOVERED_AGENT],
)
def test_non_event_sources_do_not_expire(source_kind):
    assert (
        projection_expires_at(
            source_kind,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            30,
        )
        is None
    )


def test_projection_expiry_uses_source_timestamp_and_exact_cutoff():
    source_timestamp = datetime(2026, 1, 1)  # noqa: DTZ001 - exercise naive UTC normalization
    expires_at = projection_expires_at("audit_event", source_timestamp, 30)

    assert expires_at == datetime(2026, 1, 31, tzinfo=timezone.utc)
    assert not projection_is_expired(expires_at, expires_at - timedelta(microseconds=1))
    assert projection_is_expired(expires_at, expires_at)


def test_audit_source_version_prefers_entry_hash():
    event = SimpleNamespace(entry_hash="chain-hash", id=uuid4())

    assert audit_event_source_version(event) == "chain-hash"


def test_audit_source_version_is_stable_across_mutable_updates():
    event = SimpleNamespace(
        entry_hash=None,
        id=uuid4(),
        workspace_id=uuid4(),
        ts=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source="hook",
        ai_tool="claude-code",
        tool_call="Bash",
        decision="blocked",
        rule_id="no-destructive-shell",
        rule_message="Destructive command blocked",
        updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        result_summary="first result",
    )
    first = audit_event_source_version(event)

    event.updated_at = datetime(2026, 2, 1, tzinfo=timezone.utc)
    event.result_summary = "final result"

    assert audit_event_source_version(event) == first
