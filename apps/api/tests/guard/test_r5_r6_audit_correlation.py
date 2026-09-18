"""R5 + R6 (reviewer P1) — audit-lifecycle correlation and finalize on refusal.

R5: reservations correlate to the audit row's ``request_id``, not its
``row_id``. Pre-fix the handler passed ``_durable.row_id`` as the
reservation ``request_id``; PR #2109's drawer endpoint queries the
audit ``request_id`` field which is a DIFFERENT UUID that
``insert_accepted`` generates internally. Result: even with R1's column
in place, the drawer would find zero reservations.

R6: on a fail-closed refusal the previous handler cancelled the renewal
task but never called ``finalize_durable_row`` — the row stayed in
'accepted' state until lease expiry, at which point the reconciler
reported 'orphaned' instead of the real refusal outcome.

These tests exercise the invariants at the type / structural level.
End-to-end drawer coverage requires a running FastAPI + audit stack;
that belongs in the integration suite (R2 wiring).
"""
from __future__ import annotations

import inspect

from app.modules.guard.gateway_lifecycle import DurableRow


def test_durable_row_carries_request_id():
    """R5: the handle threaded through the request lifecycle must expose
    the server-owned request_id so callers can correlate reservations
    to the audit row's request_id column (not its primary-key row_id).
    """
    field_names = {f.name for f in DurableRow.__dataclass_fields__.values()}
    assert "request_id" in field_names, (
        "DurableRow.request_id missing — reservations cannot correlate "
        "to the audit row's request_id column. See R5."
    )


def test_durable_row_request_id_defaults_to_none():
    """Pre-durable-audit paths (workspaces with the audit flag off) get
    a DurableRow with row_id=None; request_id should also be None so
    the handler's ``_audit_request_id = _durable.request_id or
    _durable_row_id`` fallback is well-defined."""
    dr = DurableRow()
    assert dr.request_id is None


def test_handler_uses_request_id_not_row_id_for_reservation():
    """R5: the handler now assigns
        _audit_request_id = _durable.request_id or _durable_row_id
    and passes _audit_request_id to reserve_budgets_for_request.
    Grep-guard against a regression to _durable_row_id."""
    import app.modules.guard.gateway_handler as gh
    src = inspect.getsource(gh)
    assert "_audit_request_id = _durable.request_id or _durable_row_id" in src, (
        "R5 correlation missing: handler must derive _audit_request_id "
        "from _durable.request_id."
    )
    # The reserve call must consume _audit_request_id, not _durable_row_id.
    # Multi-line kwargs: look at the ~700-char window starting at the call.
    reserve_call_start = src.index("_reserve_result = _reserve_budgets_for_request(")
    reserve_block = src[reserve_call_start : reserve_call_start + 700]
    assert "request_id=_audit_request_id" in reserve_block, (
        "reserve call must pass request_id=_audit_request_id (post R5). "
        "Passing _durable_row_id breaks the drawer's correlation."
    )
    assert "request_id=_durable_row_id" not in reserve_block, (
        "regressed: reserve call still passes request_id=_durable_row_id — "
        "revert to _audit_request_id per R5."
    )


def test_refusal_branch_finalizes_before_close():
    """R6: on a fail-closed refusal the handler must call
    _finalize_durable_row with decision='blocked' + a refusal rule_id
    BEFORE cancelling the renewal task. Pre-fix only close_durable was
    called; the audit row stayed 'accepted' until lease expiry."""
    import app.modules.guard.gateway_handler as gh
    src = inspect.getsource(gh)

    # Locate the fail-closed branch.
    branch_start = src.index("# Reserve failed = fail-closed reject")
    branch_end = src.index("return _budget_block_response(_reserve_result)", branch_start)
    branch = src[branch_start:branch_end]

    assert "_finalize_durable_row(" in branch, (
        "R6 fix missing: refusal branch must finalize the audit row "
        "as blocked before returning. Otherwise Flight Recorder shows "
        "'orphaned' instead of 'blocked'."
    )
    assert 'decision="blocked"' in branch, (
        "R6 refusal must record decision='blocked' on the audit row."
    )


def test_refusal_rule_ids_are_specific_per_outcome():
    """Each reserve outcome should map to a distinct rule_id so the
    drawer + Flight Recorder can label the refusal precisely (over
    cap vs unavailable vs cold-start vs generic error)."""
    import app.modules.guard.gateway_handler as gh
    src = inspect.getsource(gh)
    for rule in (
        "guard.budget_cap_exceeded",
        "guard.budget_ledger_not_ready",
        "guard.budget_ledger_unavailable",
        "guard.budget_ledger_error",
    ):
        assert rule in src, (
            f"refusal rule_id {rule!r} missing — Flight Recorder cannot "
            "distinguish this refusal cause. See R6."
        )
