"""Session 6F self-checks — pins the fixes for the 6 findings on
1219d734. Any regression surfaces at the exact bug that caused it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.contracts import (
    ExecutionOutcome,
    UsageCompleteness,
    UsageOrigin,
)


@pytest.fixture
def _shadow_on(monkeypatch):
    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", True)
    monkeypatch.setattr(settings, "guard_accounting_shadow_workspace_allowlist", "*")


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


# ─── #1 SQL column name — the metric no longer swallows the failure ─────


def test_missing_shadow_metric_reraises_on_query_failure(monkeypatch):
    """Prior code masked the ts-vs-timestamp bug by returning 0. Now
    we re-raise so callers see the failure explicitly."""
    from app.runtime.accounting import metrics

    class _BadSession:
        def execute(self, *a, **kw):
            raise RuntimeError("relation guard_audit_events does not exist")

    m = MagicMock()
    with pytest.raises(RuntimeError):
        metrics._count_settled_missing_shadow(
            _BadSession(),
            workspace_id="ws-x",
            period_start=datetime.now(timezone.utc),
            period_end=datetime.now(timezone.utc) + timedelta(hours=1),
        )


def test_reconciler_query_uses_ts_column():
    """Pin the column name in source so a rename can't silently
    reintroduce the ts-vs-timestamp bug."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler)
    assert "gae.ts >=" in src
    assert "gae.ts <" in src
    # 'gae.timestamp' MUST NOT appear (prior bug).
    assert "gae.timestamp" not in src


def test_metric_query_uses_ts_column():
    """Same pin for the metric side."""
    import inspect
    from app.runtime.accounting import metrics

    src = inspect.getsource(metrics._count_settled_missing_shadow)
    assert "gae.ts >=" in src
    assert "gae.timestamp" not in src


# ─── #2 fallback success carries preceding failure usage ───────────────


def test_success_meta_includes_failure_response_bytes_b64(_shadow_on, _captured):
    """The success attempts_meta list must carry response_bytes_b64 from
    the failed attempts, otherwise per-attempt accounting drops them
    when the request as a whole succeeds via fallback."""
    import base64
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    failed_bytes = b'{"usage":{"input_tokens":200,"output_tokens":0}}'
    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "succeeded": False,
            "error_class": "RateLimit",
            "response_bytes_b64": base64.b64encode(failed_bytes).decode("ascii"),
            "model": "claude-sonnet-4-6",
        },
        {
            "provider_or_integration": "anthropic",
            "succeeded": True,
            "model": "claude-sonnet-4-6",
        },
    ]
    write_receipts_for_attempts(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":30,"output_tokens":10}}',
        legacy_input_tokens=30,
        legacy_output_tokens=10,
        legacy_cost_usd=0.0001,
        attempts_meta=attempts_meta,
    )
    assert _captured[0].total_input_tokens == 200  # from failed attempt bytes
    assert _captured[1].total_input_tokens == 30   # from winner


# ─── #3 per-attempt model ──────────────────────────────────────────────


def test_per_attempt_model_flows_to_receipt(_shadow_on, _captured):
    """AttemptRecord.model is written into the corresponding receipt row.
    A mixed-target profile (claude → gpt fallback) must not mis-attribute."""
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    attempts_meta = [
        {
            "provider_or_integration": "anthropic",
            "succeeded": False,
            "error_class": "Overloaded",
            "model": "claude-opus-4-7",
        },
        {
            "provider_or_integration": "openai",
            "succeeded": True,
            "model": "gpt-4.1",
        },
    ]
    write_receipts_for_attempts(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-opus-4-7",  # request-level default
        operation="chat.completions",
        dispatched=True,
        response_bytes=b'{"usage":{"prompt_tokens":30,"completion_tokens":10}}',
        legacy_input_tokens=30,
        legacy_output_tokens=10,
        legacy_cost_usd=0.0001,
        attempts_meta=attempts_meta,
    )
    assert _captured[0].model == "claude-opus-4-7"
    assert _captured[1].model == "gpt-4.1"
    assert _captured[1].provider == "openai"


def test_attempt_record_model_field_present():
    """Pin AttemptRecord.model so a coordinator refactor can't silently
    strip it."""
    from dataclasses import fields
    from app.runtime.attempt_coordinator import AttemptRecord

    names = {f.name for f in fields(AttemptRecord)}
    assert "model" in names


# ─── #4 reconciler placeholder promotion ───────────────────────────────


def test_non_reconciler_write_flags_atomic_promotion(_shadow_on, monkeypatch):
    """Session 6G moved placeholder promotion from DELETE-then-INSERT to
    atomic ``INSERT ON CONFLICT DO UPDATE ... WHERE source='reconciler'``.
    Callers signal 'this is a real write' via ``is_reconciler=False`` to
    ``_persist_atomic``; the SQL clause does the guarded overwrite."""
    calls: list = []
    def _capture(_db, row, *, is_reconciler):
        calls.append(is_reconciler)
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
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
        source="gateway",
    )
    assert calls == [False]


def test_reconciler_write_flags_placeholder_mode(_shadow_on, monkeypatch):
    """Reconciler writes MUST pass ``is_reconciler=True`` so ``_persist_atomic``
    uses ``ON CONFLICT DO NOTHING`` — a placeholder never overwrites a
    real receipt."""
    calls: list = []
    def _capture(_db, row, *, is_reconciler):
        calls.append(is_reconciler)
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="reconciled",
        dispatched=True,
        response_bytes=None,
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
        source="reconciler",
    )
    assert calls == [True]


def test_persist_atomic_builds_on_conflict_do_update_for_real_writes():
    """Pin the SQL construction: non-reconciler → DO UPDATE with the
    ``source='reconciler'`` predicate. A regression to DELETE-then-INSERT
    would drop this clause."""
    import inspect
    from app.runtime.accounting import shadow_writer

    src = inspect.getsource(shadow_writer._persist_atomic)
    assert "on_conflict_do_update" in src
    assert "table.c.source == \"reconciler\"" in src
    assert "on_conflict_do_nothing" in src


def test_reconciler_join_matches_any_receipt():
    """Session 6G reviewer #3 REVERSED Session 6F's LEFT JOIN filter. The
    reconciler now matches ANY receipt (placeholder or real) so the same
    placeholders are not rescanned every pass. Placeholder-vs-real
    supersession happens in ``_persist_atomic`` via the atomic upsert."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler)
    # The old filter must be gone.
    assert "r.source IS DISTINCT FROM 'reconciler'" not in src
    # The scan is ORDER BY ts so pagination is deterministic.
    assert "ORDER BY gae.ts" in src


# ─── #6 cache-savings helper honest scope ──────────────────────────────


def test_cache_read_savings_narrow_scope_helper_present():
    """The narrow per-receipt helper exists so Lens can honestly aggregate
    across mixed-model periods."""
    from app.runtime.accounting import compute_cache_read_savings_for_receipt

    assert callable(compute_cache_read_savings_for_receipt)


def test_cache_savings_dataclass_no_longer_hardcodes_write_tokens():
    """Prior CacheSavings hardcoded ``cache_write_tokens=0`` in the
    returned dataclass. New CacheReadSavings drops the field entirely
    so callers can't mistake it for a computed value."""
    from dataclasses import fields
    from app.runtime.accounting import CacheReadSavings

    names = {f.name for f in fields(CacheReadSavings)}
    assert "cache_write_tokens" not in names
    assert "counterfactual_read_cost_microdollars" in names
