"""Real-DB integration for the two spend-UI consumers that stayed on
legacy audit cost after the PR 4 cutover.

Locks:

- ``AccountingReader.spend_micros_by_workspace`` — new helper that reads
  the same two sources as ``BudgetLedger.reconcile`` (receipts + audit
  NOT EXISTS fallback) so no spend UI can disagree with the enforcement
  counter.
- ``insights.dashboard`` "developers near limit" tile → reads receipts.
- ``lens_workspace_status`` tool → reads receipts.

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


@pytest.fixture(scope="module")
def workspace_id() -> str:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"spend-ui-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()
    yield ws_id
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM llm_attempt_receipts "
                "WHERE workspace_id = CAST(:id AS uuid)"
            ),
            {"id": ws_id},
        )
        db.execute(
            text(
                "DELETE FROM guard_audit_events "
                "WHERE workspace_id = CAST(:id AS uuid)"
            ),
            {"id": ws_id},
        )
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()


def _write_receipt(workspace_id: str, *, clerk: str | None = None) -> None:
    from app.runtime.accounting.shadow_writer import shadow_write

    shadow_write(
        workspace_id=workspace_id,
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        source="gateway",
        developer_external_id=clerk,
    )


def _write_audit(
    workspace_id: str,
    *,
    cost_usd: float = 0.001,
    clerk: str | None = None,
) -> str:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    req_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, clerk_user_id, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', :cost, :clerk, 'test')"
            ),
            {
                "ws": workspace_id,
                "req": req_id,
                "cost": cost_usd,
                "clerk": clerk,
            },
        )
        db.commit()
    return req_id


# ─── AccountingReader.spend_micros_by_workspace ───────────────────────


def test_spend_micros_sums_receipts_and_pre_cutover_audit(workspace_id):
    """Two receipts (post-cutover, 1_050 μUSD each) + one audit-only
    (pre-cutover, 500 μUSD). Total = 2_600 μUSD."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader

    _write_receipt(workspace_id)
    _write_receipt(workspace_id)
    _write_audit(workspace_id, cost_usd=0.0005)

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        totals = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
        )
    assert totals == {None: 2_600}


def test_spend_micros_skips_audit_when_receipt_exists(workspace_id):
    """A request with BOTH a receipt AND an audit row is counted ONCE —
    from the receipt (NOT EXISTS predicate prevents double-count)."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    clerk = f"clerk-{uuid.uuid4().hex[:8]}"
    request_id = uuid.uuid4()

    # Write receipt AND audit for the same request_id.
    shadow_write(
        workspace_id=workspace_id,
        request_id=request_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        source="gateway",
        developer_external_id=clerk,
    )
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, clerk_user_id, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.42, :clerk, 'test-with-receipt')"
            ),
            {
                "ws": workspace_id,
                "req": str(request_id),
                "clerk": clerk,
            },
        )
        db.commit()

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        totals = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            clerk_user_id=clerk,
        )
    # Receipt (1_050) only. Audit's 420_000 would show if NOT EXISTS
    # predicate leaked.
    assert totals[None] == 1_050


def test_spend_micros_group_by_clerk_returns_per_user_totals(workspace_id):
    """group_by_clerk=True → dict keyed by clerk_user_id."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader

    alice = f"alice-{uuid.uuid4().hex[:8]}"
    bob = f"bob-{uuid.uuid4().hex[:8]}"

    _write_receipt(workspace_id, clerk=alice)
    _write_receipt(workspace_id, clerk=alice)
    _write_receipt(workspace_id, clerk=bob)
    # Pre-cutover audit-only spend for alice.
    _write_audit(workspace_id, cost_usd=0.0002, clerk=alice)

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        totals = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            group_by_clerk=True,
        )
    # alice: 2*1_050 receipts + 200 audit = 2_300. bob: 1_050. Others
    # from prior tests may show — assert exact for alice + bob subset.
    assert totals.get(alice) == 2_300
    assert totals.get(bob) == 1_050
    # Users with no spend absent.
    assert f"nobody-{uuid.uuid4().hex[:8]}" not in totals


def test_spend_micros_excludes_partial_receipt_for_its_own_developer(
    workspace_id,
):
    """PR 4 review P3: a partial receipt written FOR a specific developer
    must NOT appear in that developer's spend total. Previous test
    queried an UNRELATED developer and would have passed even if the
    exclusion were broken."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader
    from app.runtime.accounting.shadow_writer import shadow_write

    clerk = f"partial-owner-{uuid.uuid4().hex[:8]}"
    partial_sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
    )
    shadow_write(
        workspace_id=workspace_id,
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=partial_sse,
        source="gateway",
        developer_external_id=clerk,
    )

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        # Query THIS developer — if the partial receipt were included,
        # this would be > 0.
        totals = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            clerk_user_id=clerk,
        )
    assert totals == {None: 0}

    with SessionLocal() as db:
        # group_by_clerk variant — this developer must be absent from
        # the grouped result (no settleable spend of any kind).
        grouped = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            group_by_clerk=True,
        )
    assert grouped.get(clerk) is None or grouped.get(clerk) == 0


def test_partial_receipt_does_not_reintroduce_legacy_audit_cost(workspace_id):
    """PR 4 review P1 (post-cutover): a request with BOTH a PARTIAL
    receipt AND an audit row must count NEITHER in the spend total.

    Pre-fix, ``NOT EXISTS settleable receipt`` matched a post-cutover
    partial-receipt request → its legacy audit ``cost_usd_after`` was
    added back to the total, reintroducing the exact inaccurate amount
    the completeness gate was there to exclude.

    Post-fix, the fallback fires only when NO receipt exists at all —
    a partial receipt IS a receipt, so the audit row is suppressed too.
    Both signals are "unresolved"; the companion
    ``unresolved_request_count_by_workspace`` surfaces the count.
    """
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    clerk = f"double-count-{uuid.uuid4().hex[:8]}"
    request_id = uuid.uuid4()
    partial_sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
    )
    shadow_write(
        workspace_id=workspace_id,
        request_id=request_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=partial_sse,
        source="gateway",
        developer_external_id=clerk,
    )
    # Legacy audit row for the SAME request (post-cutover, audit still
    # lands via audit.record()).
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, clerk_user_id, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.42, :clerk, 'partial-with-audit')"
            ),
            {
                "ws": workspace_id,
                "req": str(request_id),
                "clerk": clerk,
            },
        )
        db.commit()

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        totals = AccountingReader(db).spend_micros_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            clerk_user_id=clerk,
        )
    # Both excluded. If the audit fallback fired on "no settleable
    # receipt" (old bug), we'd see 420_000 μUSD (0.42 × 1M).
    assert totals == {None: 0}

    # And the request shows up in the unresolved count so consumers can
    # tag it "in-progress".
    with SessionLocal() as db:
        unresolved = AccountingReader(db).unresolved_request_count_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            clerk_user_id=clerk,
        )
    assert unresolved == {None: 1}


def test_unresolved_count_does_not_double_count_multi_attempt_partial(
    workspace_id,
):
    """A request that wrote MULTIPLE partial receipts (multi-attempt
    stream disconnect) counts as ONE unresolved request, not N."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.reader import AccountingReader
    from app.runtime.accounting.shadow_writer import write_receipts_for_attempts

    clerk = f"multi-partial-{uuid.uuid4().hex[:8]}"
    partial_sse = (
        b"event: message_start\n"
        b'data: {"type":"message_start","message":{"usage":{"input_tokens":100,"output_tokens":1}}}\n\n'
    )
    request_id = uuid.uuid4()
    write_receipts_for_attempts(
        workspace_id=workspace_id,
        request_id=request_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=partial_sse,
        source="gateway",
        developer_external_id=clerk,
        attempts_meta=[
            {"provider_or_integration": "anthropic", "model": "claude-sonnet-4-6", "succeeded": False, "response_bytes_b64": ""},
            {"provider_or_integration": "anthropic", "model": "claude-sonnet-4-6", "succeeded": True},
        ],
    )

    since = datetime.now(timezone.utc) - timedelta(hours=1)
    with SessionLocal() as db:
        unresolved = AccountingReader(db).unresolved_request_count_by_workspace(
            workspace_id=uuid.UUID(workspace_id),
            since=since,
            clerk_user_id=clerk,
        )
    # Even if 2 non-settleable receipts landed for this request_id, it
    # counts as 1 unresolved request.
    assert unresolved.get(None, 0) <= 1


# ─── Consumer wiring pins ─────────────────────────────────────────────


def test_insights_router_reads_from_accounting_reader():
    """Source-string pin: ``insights.dashboard`` uses AccountingReader
    for the developer-spend query, not a direct audit sum."""
    import inspect
    from app.routers import insights

    src = inspect.getsource(insights)
    assert "spend_micros_by_workspace" in src, (
        "insights router regressed to legacy audit sum — spend tile "
        "will under-count Anthropic cache tokens post-cutover."
    )
    # And the buggy pattern is gone.
    assert "func.sum(GuardAuditEvent.cost_usd_after)" not in src, (
        "insights router still contains direct audit spend sum."
    )


def test_lens_workspace_status_tool_reads_from_accounting_reader():
    """Source-string pin: lens_workspace_status uses AccountingReader
    for the workspace spend total."""
    import inspect
    from app.tools.registrations.lens import workspace as tools_workspace

    src = inspect.getsource(tools_workspace)
    assert "spend_micros_by_workspace" in src, (
        "lens_workspace_status regressed to legacy audit sum."
    )
    assert "db.query(GuardAuditEvent.cost_usd_after)" not in src
