"""PR 1 self-checks — Lens reads from AccountingReader, not raw audit SUM.

Ships alongside #2221 follow-up "consumer wiring". Verifies the API surface
Lens calls, the fallback for sessions with no receipts, and the flag
propagation Lens's UI needs to render caveats.
"""

from __future__ import annotations

import uuid
from dataclasses import fields

from app.runtime.accounting import (
    AccountingReader,
    SessionSpend,
)


# ─── SessionSpend contract ─────────────────────────────────────────────


def test_session_spend_is_frozen_dataclass():
    import pytest
    from dataclasses import FrozenInstanceError

    s = SessionSpend(
        hook_session_id=uuid.uuid4(),
        receipt_count=0,
        request_count=0,
        total_cost_microdollars=0,
        has_partial_or_missing=False,
        has_unpriced_attempts=False,
    )
    with pytest.raises(FrozenInstanceError):
        s.total_cost_microdollars = 999  # type: ignore[misc]


def test_session_spend_carries_completeness_flags():
    """PR 1 promise: Lens's UI can tell reported vs partial vs unpriced
    apart. Pin the fields on the aggregate so the flags cannot vanish
    silently in a future refactor."""
    names = {f.name for f in fields(SessionSpend)}
    assert names >= {
        "hook_session_id",
        "receipt_count",
        "request_count",
        "total_cost_microdollars",
        "has_partial_or_missing",
        "has_unpriced_attempts",
    }


def test_total_cost_usd_property_converts_microdollars():
    from decimal import Decimal

    s = SessionSpend(
        hook_session_id=uuid.uuid4(),
        receipt_count=1,
        request_count=1,
        total_cost_microdollars=1_234_567,
        has_partial_or_missing=False,
        has_unpriced_attempts=False,
    )
    assert s.total_cost_usd == Decimal("1.234567")


# ─── AccountingReader.spend_by_hook_session_ids ───────────────────────


def test_spend_by_hook_session_ids_empty_input_returns_empty_dict():
    """No sessions to look up ⇒ no query, empty dict. Lens's list-view
    is common enough that we short-circuit."""
    from unittest.mock import MagicMock

    reader = AccountingReader(MagicMock())
    result = reader.spend_by_hook_session_ids(
        workspace_id=uuid.uuid4(),
        hook_session_ids=[],
    )
    assert result == {}


def test_spend_by_hook_session_ids_method_present_with_expected_signature():
    """Pin the API surface Lens consumes so a future refactor cannot
    silently drop the batched entry point."""
    import inspect

    sig = inspect.signature(AccountingReader.spend_by_hook_session_ids)
    params = list(sig.parameters.keys())
    assert "workspace_id" in params
    assert "hook_session_ids" in params


# ─── Lens router wiring (source-string pins) ───────────────────────────


def test_lens_sessions_router_no_longer_sums_guard_audit_event():
    """The old ``SUM(GuardAuditEvent.cost_usd_after)`` query is gone.
    Sessions router now consumes AccountingReader; every number Lens
    displays comes from the shared accounting engine (per Sudhi's
    2026-09-23 split of accounting vs Lens epics)."""
    import inspect
    from app.modules.glens.routers import lens_sessions

    src = inspect.getsource(lens_sessions)
    assert "GuardAuditEvent.cost_usd_after" not in src
    assert "AccountingReader" in src
    assert "spend_by_hook_session_ids" in src


def test_lens_sessions_output_exposes_spend_completeness_flags():
    """Lens's session-list response carries the caveats the UI must
    render alongside the number."""
    from app.modules.glens.routers.lens_sessions import LensSessionOut

    fields_set = set(LensSessionOut.model_fields.keys())
    assert "spend_has_partial_or_missing" in fields_set
    assert "spend_has_unpriced_attempts" in fields_set
