"""Shadow writer self-checks (#2209 Session 4).

Uses a MagicMock SessionLocal so tests do not require a live Postgres.
The Postgres-backed integration test lands in
tests/integration/test_shadow_writer_realdb.py (Session 6) — same pattern
as the durable audit lifecycle tests.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.runtime.accounting.contracts import (
    ExecutionOutcome,
    PricingCompleteness,
    UsageCompleteness,
    UsageOrigin,
)
from app.runtime.accounting.shadow_writer import shadow_write


@pytest.fixture
def _shadow_on(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", True)
    yield


@pytest.fixture
def _shadow_off(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", False)
    yield


@pytest.fixture
def _captured_row(monkeypatch):
    """Intercept _persist_atomic and return whatever row was persisted.

    #2209 Session 6G: the writer now uses ``INSERT ... ON CONFLICT ... DO
    UPDATE`` via SQLAlchemy Core so a mocked ``session.add`` wouldn't fire.
    Tests hook the extracted persist helper instead — captures the ORM
    row exactly as before.
    """
    captured: dict = {}

    def _capture(_db, row, *, is_reconciler):
        captured["row"] = row
        captured["is_reconciler"] = is_reconciler
        return row.id  # simulate successful insert; matches RETURNING id

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    # SessionLocal still gets opened; keep it a no-op MagicMock so the
    # writer can call db.commit() / db.close() without raising.
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    return captured


def test_shadow_off_never_writes(_shadow_off, _captured_row):
    result = shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )
    assert result is None
    assert "row" not in _captured_row


def test_shadow_on_writes_anthropic_json(_shadow_on, _captured_row):
    ws_id = uuid.uuid4()
    req_id = uuid.uuid4()
    result = shadow_write(
        workspace_id=ws_id,
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"cache_read_input_tokens":20,"output_tokens":40}}',
        legacy_input_tokens=100,
        legacy_output_tokens=40,
        legacy_cost_usd=0.00090,
    )
    assert result is not None
    row = _captured_row["row"]
    assert row.workspace_id == ws_id
    assert row.request_id == req_id
    assert row.provider == "anthropic"
    assert row.model == "claude-sonnet-4-6"
    assert row.attempt_ordinal == 0
    # New normalizer picked up cache_read_input_tokens
    assert row.cache_read_tokens == 20
    assert row.total_output_tokens == 40
    # Legacy fields populated for shadow comparison
    assert row.legacy_input_tokens == 100
    assert row.legacy_output_tokens == 40
    assert row.legacy_cost_microdollars == 900  # 0.0009 * 1_000_000
    assert row.execution_outcome == ExecutionOutcome.SUCCEEDED.value
    assert row.usage_origin == UsageOrigin.PROVIDER_REPORTED.value
    assert row.usage_completeness == UsageCompleteness.COMPLETE.value


def test_shadow_on_writes_openai_json(_shadow_on, _captured_row):
    result = shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="openai",
        model="gpt-4.1",
        operation="chat.completions",
        dispatched=True,
        response_bytes=b'{"usage":{"prompt_tokens":1000,"completion_tokens":50,"prompt_tokens_details":{"cached_tokens":400}}}',
        legacy_input_tokens=1000,
        legacy_output_tokens=50,
        legacy_cost_usd=None,
    )
    assert result is not None
    row = _captured_row["row"]
    assert row.total_input_tokens == 1000
    assert row.cache_read_tokens == 400
    assert row.uncached_input_tokens == 600
    assert row.total_output_tokens == 50


def test_shadow_uses_responses_normalizer_when_operation_matches(_shadow_on, _captured_row):
    """Responses API uses input_tokens/output_tokens (different from prompt/completion)."""
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="openai",
        model="gpt-5",
        operation="/v1/responses",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":200,"output_tokens":30}}',
        legacy_input_tokens=200,
        legacy_output_tokens=30,
        legacy_cost_usd=None,
    )
    row = _captured_row["row"]
    assert row.total_input_tokens == 200
    assert row.total_output_tokens == 30


def test_shadow_on_writes_anthropic_sse(_shadow_on, _captured_row):
    sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"cache_read_input_tokens":20,"output_tokens":1}}}\n\n'
        b"event: message_delta\n"
        b'data: {"type":"message_delta","usage":{"output_tokens":50}}\n\n'
        b"event: message_stop\n"
        b'data: {"type":"message_stop"}\n\n'
    )
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=sse,
        legacy_input_tokens=120,
        legacy_output_tokens=50,
        legacy_cost_usd=0.001,
    )
    row = _captured_row["row"]
    assert row.usage_origin == UsageOrigin.NORMALIZED_STREAM.value
    assert row.total_output_tokens == 50
    assert row.cache_read_tokens == 20


def test_shadow_captures_not_dispatched_as_preflight_reject(_shadow_on, _captured_row):
    """A request rejected before dispatch has no usage but should still write a
    receipt row so ops can see the reservation activity."""
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="openai",
        model="gpt-4.1",
        operation="chat.completions",
        dispatched=False,
        response_bytes=None,
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
    )
    row = _captured_row["row"]
    assert row.execution_outcome == ExecutionOutcome.REJECTED_PREFLIGHT.value
    assert row.usage_completeness == UsageCompleteness.UNAVAILABLE.value
    assert row.total_input_tokens is None
    assert row.total_output_tokens is None


def test_shadow_captures_dispatched_with_no_bytes_as_failed(_shadow_on, _captured_row):
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=None,
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
    )
    row = _captured_row["row"]
    assert row.execution_outcome == ExecutionOutcome.FAILED.value
    assert row.usage_completeness == UsageCompleteness.UNAVAILABLE.value


def test_shadow_never_raises_on_bad_input(_shadow_on, _captured_row):
    """Corrupt UUID, non-dict response, garbage bytes — never raises."""
    result = shadow_write(
        workspace_id="not-a-uuid",  # type: ignore[arg-type]
        request_id="not-a-uuid",  # type: ignore[arg-type]
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b"garbage_not_json_not_sse",
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
    )
    # Either wrote a receipt with UNAVAILABLE or returned None on write failure —
    # both acceptable; the important assertion is it did not raise.
    assert result is None or result is not None


def test_shadow_records_attempts_meta_in_provenance(_shadow_on, _captured_row):
    """The routing_meta.attempts array is preserved in provenance so per-
    attempt cost breakdowns are available for Session 5+ analysis."""
    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="openai",
        model="gpt-4.1",
        operation="chat.completions",
        dispatched=True,
        response_bytes=b'{"usage":{"prompt_tokens":10,"completion_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.00002,
        attempts_meta=[
            {"target_id": "primary", "provider": "openai", "succeeded": True},
        ],
    )
    row = _captured_row["row"]
    assert "attempts" in row.calculation_provenance
    assert row.calculation_provenance["attempts"][0]["target_id"] == "primary"


def test_shadow_swallows_db_error(_shadow_on, monkeypatch):
    """Even if the DB throws, shadow_write returns None and does not propagate."""
    def _boom(*_a, **_kw):
        raise RuntimeError("db exploded")
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _boom
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    result = shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )
    assert result is None


def test_contract_version_recorded_on_row(_shadow_on, _captured_row):
    from app.runtime.accounting.contracts import CONTRACT_VERSION

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )
    row = _captured_row["row"]
    assert row.contract_version == CONTRACT_VERSION
    assert row.normalizer_version  # non-empty
