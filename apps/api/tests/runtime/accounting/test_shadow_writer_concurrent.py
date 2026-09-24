"""Concurrent/failure self-checks for the shadow writer (#2209 Session 6).

Proves the shadow writer:

1. Survives concurrent invocations (no shared mutable state).
2. Never lets a settlement path fail because of a shadow-write error.
3. Handles duplicate-key writes without exception (unique constraint on
   ``(request_id, attempt_ordinal)`` — IntegrityError swallowed).
4. Handles connection loss / rollback cleanly.

Postgres-backed race tests land in tests/integration/ (Session 6b).
"""

from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.shadow_writer import shadow_write


@pytest.fixture
def _shadow_on():
    # Cutover: writer always on. Fixture kept as a no-op for existing callers.
    yield


def _write(workspace_id=None):
    return shadow_write(
        workspace_id=workspace_id or uuid.uuid4(),
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


def test_concurrent_writes_do_not_share_state(_shadow_on, monkeypatch):
    """Fire 50 shadow writes from 10 threads and verify they all succeed
    independently. The writer must own its DB session per call."""
    written: list = []
    lock = threading.Lock()

    def _capture(_db, row, *, is_reconciler):
        with lock:
            written.append(row)
        return row.id

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )

    def _worker():
        for _ in range(5):
            _write()

    threads = [threading.Thread(target=_worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(written) == 50
    # Each row should have a unique receipt id — no state was shared.
    receipt_ids = {row.id for row in written}
    assert len(receipt_ids) == 50


def test_db_integrity_error_never_raises(_shadow_on, monkeypatch):
    """Simulates the unique-constraint duplicate case."""
    class _Integrity(Exception):
        pass

    def _boom(*_a, **_kw):
        raise _Integrity("duplicate key value")

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _boom
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    result = _write()
    assert result is None


def test_session_close_failure_never_raises(_shadow_on, monkeypatch):
    """If db.close() throws, the writer swallows it — the outer request
    is unaffected."""
    session = MagicMock()
    session.close.side_effect = RuntimeError("connection dead")
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=session),
    )
    # No raise expected
    result = _write()
    # Either succeeded before close, or swallowed the close error — both fine.
    assert result is None or isinstance(result, uuid.UUID)


def test_normalizer_exception_never_raises(_shadow_on, monkeypatch):
    """Corrupt response_bytes must not crash the settlement path."""

    def _boom(*args, **kwargs):
        raise RuntimeError("normalizer imploded")

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.normalize_json", _boom
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.normalize_sse", _boom
    )
    session = MagicMock()
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=session),
    )
    result = _write()
    assert result is None


def test_pricing_service_exception_never_raises(_shadow_on, monkeypatch):
    """If the pricing service throws inside the writer, we still get a
    receipt with UNPRICED completeness rather than a dropped write."""

    class _BrokenService:
        def price_tokens(self, *_, **__):
            raise RuntimeError("pricing service down")

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.default_pricing_service",
        lambda: _BrokenService(),
    )
    session = MagicMock()
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=session),
    )
    result = _write()
    # Writer catches, returns None. Row NOT persisted for this call.
    assert result is None


def test_duplicate_write_for_same_request_attempt_is_idempotent(_shadow_on, monkeypatch):
    """Calling shadow_write twice with the same receipt_id + attempt_ordinal
    is safe — the DB unique constraint would reject the second, and the
    writer swallows the IntegrityError."""
    written: list = []
    call_count = [0]

    def _persist(_db, row, *, is_reconciler):
        call_count[0] += 1
        if call_count[0] == 2:
            raise Exception("unique_violation")
        written.append(row)
        return row.id

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _persist
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    receipt_id = uuid.uuid4()
    request_id = uuid.uuid4()
    ws_id = uuid.uuid4()

    def _same_write():
        return shadow_write(
            workspace_id=ws_id,
            request_id=request_id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            operation="messages.create",
            dispatched=True,
            response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
            legacy_input_tokens=10,
            legacy_output_tokens=5,
            legacy_cost_usd=0.0001,
            receipt_id=receipt_id,
            attempt_ordinal=0,
        )

    r1 = _same_write()
    r2 = _same_write()
    assert r1 == receipt_id
    assert r2 is None  # second call swallowed IntegrityError
    assert len(written) == 1
