"""Session 6G self-checks — pins the fixes for the 3 findings on 42d89898."""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.runtime.accounting.contracts import UsageCompleteness


@pytest.fixture
def _shadow_on(monkeypatch):
    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", True)
    monkeypatch.setattr(settings, "guard_accounting_shadow_workspace_allowlist", "*")


@pytest.fixture
def _captured(monkeypatch):
    rows: list = []
    def _capture(_db, row, *, is_reconciler):
        rows.append(row)
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer._persist_atomic", _capture
    )
    monkeypatch.setattr(
        "app.runtime.accounting.shadow_writer.SessionLocal",
        MagicMock(return_value=MagicMock()),
    )
    return rows


# ─── #1 partial-usage override for streaming ───────────────────────────


def test_usage_completeness_override_partial_wins_over_normalizer(_shadow_on, _captured):
    """Reviewer #1 (#2221 review at 42d89898): synthetic JSON with
    input=100/output=0 would normalize to COMPLETE. When the caller
    knows the terminal frame never arrived, the override reclassifies
    the row PARTIAL."""
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":0}}',
        legacy_input_tokens=100,
        legacy_output_tokens=0,
        legacy_cost_usd=0.0003,
        usage_completeness_override=UsageCompleteness.PARTIAL.value,
    )
    assert _captured[0].usage_completeness == UsageCompleteness.PARTIAL.value
    # Tokens still recorded — the number is real, the completeness is
    # the caveat.
    assert _captured[0].total_input_tokens == 100


def test_usage_completeness_override_absent_leaves_normalizer_decision(_shadow_on, _captured):
    """Backwards-compat: when the caller doesn't override, the normalizer
    still decides. Reported non-zero output stays COMPLETE."""
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=uuid.uuid4(),
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        legacy_input_tokens=100,
        legacy_output_tokens=50,
        legacy_cost_usd=0.001,
    )
    assert _captured[0].usage_completeness == UsageCompleteness.COMPLETE.value


def test_openai_stream_exposes_last_usage_final_flag():
    """Pin the adapter contract Lens hook depends on."""
    import inspect
    from app.runtime.llm_client import OpenAIClient

    src = inspect.getsource(OpenAIClient.stream)
    assert "self.last_usage_final = False" in src
    assert "self.last_usage_final = True" in src


def test_anthropic_stream_marks_final_only_on_message_delta():
    """message_start sets input tokens but is not terminal. Only
    message_delta flips ``last_usage_final=True``."""
    import inspect
    from app.runtime.llm_client import AnthropicClient

    src = inspect.getsource(AnthropicClient.stream)
    assert "self.last_usage_final = False" in src
    assert "self.last_usage_final = True" in src
    # Toggle appears inside the message_delta branch, NOT message_start.
    delta_idx = src.find('"message_delta"')
    final_toggle_idx = src.find("self.last_usage_final = True")
    assert delta_idx < final_toggle_idx


def test_lens_stream_passes_partial_override_on_interruption():
    """Pin the Lens hook logic: when the stream did NOT complete normally
    or did NOT see a terminal frame, it MUST pass PARTIAL override."""
    import inspect
    from app.guard import gateway as _gw

    src = inspect.getsource(_gw.guarded_client_stream)
    assert "usage_completeness_override" in src
    assert "UsageCompleteness.PARTIAL.value" in src


# ─── #2 atomic upsert ─────────────────────────────────────────────────


def test_persist_atomic_uses_on_conflict_do_update_for_real_writes():
    """Reviewer #2 (#2221 review at 42d89898): DELETE-then-INSERT had a
    race window. Now the single-statement upsert with
    ``WHERE source = 'reconciler'`` promotes placeholders atomically."""
    import inspect
    from app.runtime.accounting import shadow_writer

    src = inspect.getsource(shadow_writer._persist_atomic)
    assert "on_conflict_do_update" in src
    assert "table.c.source == \"reconciler\"" in src
    assert "on_conflict_do_nothing" in src
    # No stray DELETE (the prior race pattern).
    assert "DELETE FROM llm_attempt_receipts" not in src


def test_persist_atomic_id_column_excluded_from_do_update_set():
    """The atomic upsert overwrites every column EXCEPT ``id`` — swapping
    the primary key of a promoted placeholder would break any FK
    references Lens might already hold."""
    import inspect
    from app.runtime.accounting import shadow_writer

    src = inspect.getsource(shadow_writer._persist_atomic)
    assert 'c.name != "id"' in src


# ─── #3 reconciler pagination + placeholder-only metric ───────────────


def test_reconciler_scan_matches_any_receipt_type():
    """Session 6G reverses Session 6F's join filter. Reconciler now
    matches ANY receipt (placeholder or real), so placeholders are not
    rescanned every pass and the LIMIT progresses to fresh gaps."""
    import inspect
    from app.runtime.accounting import reconciler

    src = inspect.getsource(reconciler)
    assert "r.source IS DISTINCT FROM 'reconciler'" not in src
    assert "ORDER BY gae.ts" in src


def test_shadow_delta_report_carries_placeholder_only_count():
    """Session 6G reviewer #3: placeholder-only requests are counted
    separately so ops sees the gap without the reconciler being trapped
    in a rescan loop."""
    from dataclasses import fields
    from app.runtime.accounting import ShadowDeltaReport

    names = {f.name for f in fields(ShadowDeltaReport)}
    assert "settled_requests_placeholder_only_count" in names


def test_placeholder_only_metric_helper_present():
    """The new helper exists — Session 7 gate criterion 5 now covers
    both `missing_shadow` and `placeholder_only` trending down."""
    from app.runtime.accounting import metrics

    assert hasattr(metrics, "_count_settled_placeholder_only")
