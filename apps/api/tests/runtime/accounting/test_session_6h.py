"""Session 6H self-checks — attempt-level reconciliation from routing_meta."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ─── Pure helper coverage (no DB needed) ────────────────────────────────


def test_extract_attempts_from_dict_meta():
    from app.runtime.accounting.reconciler import _extract_attempts_from_meta

    meta = {
        "attempts": [
            {"succeeded": False, "provider_or_integration": "anthropic"},
            {"succeeded": True, "provider_or_integration": "openai"},
        ]
    }
    total, keyed = _extract_attempts_from_meta(meta)
    assert total == 2
    assert keyed[1]["provider_or_integration"] == "openai"


def test_extract_attempts_from_stringified_meta():
    """Some DB drivers return JSONB as a string. Handle that."""
    import json
    from app.runtime.accounting.reconciler import _extract_attempts_from_meta

    meta_str = json.dumps({"attempts": [{"succeeded": True}]})
    total, keyed = _extract_attempts_from_meta(meta_str)
    assert total == 1
    assert 0 in keyed


def test_extract_attempts_from_missing_meta_returns_empty():
    """Legacy audit rows without routing_meta.attempts return (0, {}) so
    the caller defaults to a single expected ordinal {0}."""
    from app.runtime.accounting.reconciler import _extract_attempts_from_meta

    assert _extract_attempts_from_meta(None) == (0, {})
    assert _extract_attempts_from_meta({}) == (0, {})
    assert _extract_attempts_from_meta({"other_field": "x"}) == (0, {})
    assert _extract_attempts_from_meta("not-json{{") == (0, {})


def test_extract_attempts_preserves_ordinals_around_bad_entries():
    """Session 6J reviewer #6 (#2221 review at bbcb5388): non-dict
    entries reserve their ordinal slot instead of compressing the
    array. ``[attempt0, null, attempt2]`` now returns
    ``total=3, keyed={0: attempt0, 2: attempt2}`` — never
    ``total=2, keyed={0: attempt0, 1: attempt2}``."""
    from app.runtime.accounting.reconciler import _extract_attempts_from_meta

    total, keyed = _extract_attempts_from_meta(
        {"attempts": [{"provider_or_integration": "a"}, None, "bogus", 42, {"provider_or_integration": "e"}]}
    )
    assert total == 5
    assert set(keyed.keys()) == {0, 4}
    assert keyed[0]["provider_or_integration"] == "a"
    assert keyed[4]["provider_or_integration"] == "e"


# ─── Placeholder writer per-attempt behavior ─────────────────────────────


@pytest.fixture
def _captured_shadow_calls(monkeypatch):
    """Intercept shadow_write to inspect what the reconciler passes for
    each missing attempt. Returns list of kwargs dicts."""
    calls: list = []

    def _fake_shadow_write(**kw):
        calls.append(kw)
        return uuid.uuid4()  # simulate success

    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.shadow_write", _fake_shadow_write
    )
    return calls


def _fake_audit_row(**overrides):
    """Build a duck-typed audit row for the placeholder writer."""
    from types import SimpleNamespace

    base = dict(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        clerk_user_id="user_x",
        ai_tool="lens",
        tokens_after=42,
        cost_usd_after=0.001,
        audit_ts=datetime.now(timezone.utc),
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_placeholder_write_bypasses_canary_via_pinned_flag(_captured_shadow_calls):
    """Reconciler is manual/opt-in — it MUST pass
    pinned_shadow_enabled=True so the write happens regardless of the
    workspace allowlist."""
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(_fake_audit_row(), 0, {"succeeded": True})
    assert _captured_shadow_calls[0]["pinned_shadow_enabled"] is True


def test_placeholder_carries_source_reconciler(_captured_shadow_calls):
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(_fake_audit_row(), 0, {"succeeded": True})
    assert _captured_shadow_calls[0]["source"] == "reconciler"


def test_placeholder_decodes_failed_attempt_bytes(_captured_shadow_calls):
    """Failed attempts with response_bytes_b64 → placeholder gets the
    decoded bytes for normalization + pricing."""
    from app.runtime.accounting.reconciler import _write_placeholder

    envelope = b'{"error":{"type":"rate_limit"},"usage":{"input_tokens":80}}'
    _write_placeholder(
        _fake_audit_row(),
        1,
        {
            "succeeded": False,
            "provider_or_integration": "anthropic",
            "response_bytes_b64": base64.b64encode(envelope).decode("ascii"),
        },
    )
    assert _captured_shadow_calls[0]["response_bytes"] == envelope


def test_placeholder_legacy_tokens_only_on_winning_attempt(_captured_shadow_calls):
    """Audit tokens_after / cost_usd_after belong to the WINNING attempt.
    Failed-attempt placeholders must NOT inherit them."""
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(_fake_audit_row(), 0, {"succeeded": False})
    _write_placeholder(_fake_audit_row(), 1, {"succeeded": True})
    assert _captured_shadow_calls[0]["legacy_output_tokens"] is None
    assert _captured_shadow_calls[0]["legacy_cost_usd"] is None
    assert _captured_shadow_calls[1]["legacy_output_tokens"] == 42
    assert _captured_shadow_calls[1]["legacy_cost_usd"] == 0.001


def test_placeholder_per_attempt_provider_and_model_override_audit_defaults(
    _captured_shadow_calls,
):
    """Mixed-target profile: audit row provider=anthropic; attempt 1
    fell back to openai/gpt-4.1. Placeholder MUST use per-attempt
    metadata, not the audit row's request-level fields."""
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(
        _fake_audit_row(),
        1,
        {
            "succeeded": True,
            "provider_or_integration": "openai",
            "model": "gpt-4.1",
        },
    )
    assert _captured_shadow_calls[0]["provider"] == "openai"
    assert _captured_shadow_calls[0]["model"] == "gpt-4.1"


def test_placeholder_uses_reconciled_late_outcome_for_succeeded_attempts(
    _captured_shadow_calls,
):
    """Successful attempts get RECONCILED_LATE (not SUCCEEDED) so
    Session 7 activation review can spot which rows came from backfill."""
    from app.runtime.accounting.contracts import ExecutionOutcome
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(_fake_audit_row(), 0, {"succeeded": True})
    assert (
        _captured_shadow_calls[0]["execution_outcome"]
        == ExecutionOutcome.RECONCILED_LATE.value
    )


def test_placeholder_failed_attempts_keep_failed_outcome(
    _captured_shadow_calls,
):
    """Failed attempts stay FAILED, not RECONCILED_LATE — the fact
    they failed is more useful than the fact we reconciled them."""
    from app.runtime.accounting.contracts import ExecutionOutcome
    from app.runtime.accounting.reconciler import _write_placeholder

    _write_placeholder(_fake_audit_row(), 0, {"succeeded": False})
    assert (
        _captured_shadow_calls[0]["execution_outcome"]
        == ExecutionOutcome.FAILED.value
    )


# ─── Existing-ordinals lookup + missing-set logic ───────────────────────


def test_existing_ordinals_batched_query_shape():
    """Pin the batched-query SQL — one round-trip per reconcile pass,
    not per request."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler._fetch_existing_ordinals)
    assert "request_id = ANY(:ids)" in src
    assert "SELECT request_id, attempt_ordinal" in src


def test_result_dataclass_carries_attempts_expected_field():
    """New field lets ops see attempt-level coverage, not just
    request-level."""
    from dataclasses import fields
    from app.runtime.accounting import ReconciliationResult

    names = {f.name for f in fields(ReconciliationResult)}
    assert "attempts_expected" in names


def test_scan_no_longer_left_joins_receipts():
    """Session 6H moved gap detection from LEFT JOIN (request-grain) to
    per-attempt set difference in Python. The scan MUST NOT re-add the
    LEFT JOIN or it'll drop back to request-grain behavior."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler._fetch_audit_rows)
    assert "LEFT JOIN llm_attempt_receipts" not in src


# ─── High-level: reconcile function skips requests with all ordinals present ─


def test_reconcile_writes_nothing_when_all_expected_ordinals_present(monkeypatch):
    """When every expected ordinal already has a receipt, reconciler
    writes nothing — even though placeholders may exist among them."""
    from app.runtime.accounting import reconcile_missing_receipts

    session = MagicMock()

    def _execute(sql, params=None):
        result = MagicMock()
        sql_str = str(sql)
        if "FROM guard_audit_events" in sql_str:
            # One audit row with 2 attempts in routing_meta
            row = MagicMock()
            row.workspace_id = uuid.uuid4()
            row.request_id = uuid.uuid4()
            row.provider = "anthropic"
            row.model = "claude-sonnet-4-6"
            row.clerk_user_id = "user_x"
            row.ai_tool = "lens"
            row.tokens_after = 10
            row.cost_usd_after = 0.0001
            row.audit_ts = datetime.now(timezone.utc)
            row.routing_meta = {
                "attempts": [
                    {"succeeded": False, "provider_or_integration": "anthropic"},
                    {"succeeded": True, "provider_or_integration": "openai"},
                ]
            }
            result.all.return_value = [row]
        elif "FROM llm_attempt_receipts" in sql_str:
            # Both ordinals already present
            req_id = params["ids"][0] if params else uuid.uuid4()
            r0 = MagicMock(); r0.request_id = req_id; r0.attempt_ordinal = 0
            r1 = MagicMock(); r1.request_id = req_id; r1.attempt_ordinal = 1
            result.all.return_value = [r0, r1]
        else:
            result.all.return_value = []
        return result

    session.execute.side_effect = _execute
    monkeypatch.setattr(
        "app.runtime.accounting.reconciler.SessionLocal",
        MagicMock(return_value=session),
    )

    calls: list = []
    def _fake_write(**kw):
        calls.append(kw)
        return uuid.uuid4()
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.shadow_write", _fake_write
    )

    now = datetime.now(timezone.utc)
    result = reconcile_missing_receipts(
        workspace_id=str(uuid.uuid4()),
        period_start=now - timedelta(hours=1),
        period_end=now,
    )
    assert result.audit_rows_scanned == 1
    assert result.attempts_expected == 2
    assert result.receipts_written == 0
    assert len(calls) == 0
