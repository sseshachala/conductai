"""Session 6D self-checks — coordinator per-attempt bytes, version pin,
workflow linkage, reconciler (#2209).

Postgres-backed race + crash-recovery tests land in
tests/integration/test_shadow_receipts_realdb.py (Session 6D b).
"""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.contracts import (
    ExecutionOutcome,
    UsageCompleteness,
    UsageOrigin,
)


@pytest.fixture
def _shadow_on():
    # Cutover: writer always on. Fixture kept as a no-op for existing callers.
    yield


@pytest.fixture
def _captured(monkeypatch):
    rows: list = []
    def _capture(_db, row, *, is_reconciler):
        rows.append(row)
        return row.id
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    return rows


# ─── #1 coordinator captures per-attempt response bytes ───────────────────


def test_coordinator_captures_failed_response_bytes_from_httpx_error():
    """When httpx.HTTPStatusError.response.content carries the provider
    error envelope, AttemptRecord preserves it base64-encoded so per-
    attempt accounting can normalize + price it."""
    from app.runtime.attempt_coordinator import _capture_failed_response_bytes

    class _FakeResp:
        content = b'{"error":{"type":"rate_limit","message":"slow down"}}'

    class _FakeHTTPError(Exception):
        response = _FakeResp()

    b64 = _capture_failed_response_bytes(_FakeHTTPError("429"))
    assert b64 is not None
    decoded = base64.b64decode(b64)
    assert b"rate_limit" in decoded


def test_coordinator_returns_none_for_exceptions_without_response():
    from app.runtime.attempt_coordinator import _capture_failed_response_bytes

    class _NakedError(Exception):
        pass

    assert _capture_failed_response_bytes(_NakedError("boom")) is None


def test_coordinator_caps_captured_bytes_at_64kib():
    """A runaway provider error page must not bloat the audit row unbounded."""
    from app.runtime.attempt_coordinator import _capture_failed_response_bytes

    class _FakeResp:
        content = b"x" * 200_000

    class _FakeErr(Exception):
        response = _FakeResp()

    b64 = _capture_failed_response_bytes(_FakeErr())
    assert b64 is not None
    decoded = base64.b64decode(b64)
    assert len(decoded) == 65_536


def test_shadow_writer_uses_per_attempt_response_bytes_b64_from_meta(_shadow_on, _captured):
    """When attempts_meta carries response_bytes_b64 for a failed attempt,
    the writer decodes and passes those bytes so the normalizer picks
    up the provider's error envelope usage (if any)."""
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    # Failed attempt uses Anthropic-shape usage (matches its provider).
    failed_bytes = b'{"usage":{"input_tokens":100,"output_tokens":0}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "succeeded": False,
            "error_class": "RateLimit",
            "response_bytes_b64": base64.b64encode(failed_bytes).decode("ascii"),
        },
        {
            "provider_or_integration": "anthropic",  # same family so winner
            "succeeded": True,                       # normalizer aligns
        },
    ]
    write_receipts_for_attempts(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":50,"output_tokens":25}}',
        legacy_input_tokens=50,
        legacy_output_tokens=25,
        legacy_cost_usd=0.001,
        attempts_meta=attempts_meta,
    )
    assert len(_captured) == 2
    # Failed attempt (0) picked up the 100 input tokens from its captured bytes.
    assert _captured[0].total_input_tokens == 100
    assert _captured[0].execution_outcome == ExecutionOutcome.FAILED.value
    # Winner (1) got the handler's response_bytes.
    assert _captured[1].total_input_tokens == 50


def test_response_bytes_b64_is_stripped_from_stored_provenance(_shadow_on, _captured):
    """The raw base64 payload is already normalized into the row's own
    columns — don't duplicate it into calculation_provenance where it
    would bloat the JSONB."""
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    write_receipts_for_attempts(
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
        attempts_meta=[
            {
                "provider_or_integration": "anthropic",
                "succeeded": False,
                "response_bytes_b64": base64.b64encode(b"x" * 500).decode("ascii"),
            }
        ],
    )
    stored_attempts = _captured[0].calculation_provenance.get("attempts", [])
    assert stored_attempts
    assert "response_bytes_b64" not in stored_attempts[0]


# ─── #2 accounting-version pin ────────────────────────────────────────────
# Removed at cutover (PR 4): the writer is always on and always writes at
# ``CONTRACT_VERSION``. Handler-side pinning of a request's contract
# version at entry made sense while dual-engine machinery lived in the
# writer; with only one engine, mid-flight flag flips do not exist.


# ─── #4 workflow linkage ──────────────────────────────────────────────────


def test_workflow_run_id_uuid_populated_on_receipt(_shadow_on, _captured):
    from app.runtime.accounting.shadow_writer import shadow_write

    wf_run = uuid.uuid4()
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
        workflow_run_id=wf_run,
    )
    assert _captured[0].workflow_run_id == wf_run


def test_workflow_run_id_string_form_parsed(_shadow_on, _captured):
    """Headers arrive as strings — the writer parses to UUID."""
    from app.runtime.accounting.shadow_writer import shadow_write

    wf_run = uuid.uuid4()
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
        workflow_run_id=str(wf_run),
    )
    assert _captured[0].workflow_run_id == wf_run


def test_workflow_run_id_non_uuid_ignored(_shadow_on, _captured):
    """A garbage header value must not fail the write — column stays NULL."""
    from app.runtime.accounting.shadow_writer import shadow_write

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
        workflow_run_id="not-a-uuid",
    )
    assert _captured[0].workflow_run_id is None


# ─── #3 reconciler ────────────────────────────────────────────────────────


def test_reconciler_returns_zero_result_on_scan_error(monkeypatch):
    """A malformed audit table (schema drift, dropped column) must return
    a graceful zero-result, not crash the caller."""
    from app.runtime.accounting import reconcile_missing_receipts

    session = MagicMock()
    session.execute.side_effect = RuntimeError("relation guard_audit_events does not exist")
    monkeypatch.setattr(
        "app.runtime.accounting.reconciler.SessionLocal",
        MagicMock(return_value=session),
    )

    now = datetime.now(timezone.utc)
    result = reconcile_missing_receipts(
        workspace_id=str(uuid.uuid4()),
        period_start=now - timedelta(hours=1),
        period_end=now,
    )
    assert result.errors == 1
    assert result.audit_rows_scanned == 0
    assert result.receipts_written == 0


def test_reconciler_result_dataclass_frozen():
    from app.runtime.accounting import ReconciliationResult
    from dataclasses import FrozenInstanceError

    r = ReconciliationResult(
        workspace_id="ws",
        period_start=datetime.now(timezone.utc),
        period_end=datetime.now(timezone.utc),
        audit_rows_scanned=0,
        attempts_expected=0,
        receipts_written=0,
        receipts_skipped=0,
        errors=0,
    )
    with pytest.raises(FrozenInstanceError):
        r.receipts_written = 1  # type: ignore[misc]
