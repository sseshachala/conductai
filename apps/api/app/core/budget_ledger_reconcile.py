"""Budget ledger Redis rebuild from the durable log (mixin).

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

import uuid

import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.budget_ledger_keys import (
    _is_transport,
    _looks_like_uuid,
    _period_start,
    _scope_keys,
    _seconds_until_next_period,
    monthly_period_key,
)
from app.core.budget_ledger_types import (
    _MICROS_PER_CENT,
)

log = structlog.get_logger()


class _LedgerReconcileMixin:
    # ── Reconciler ──────────────────────────────────────────────────
    def reconcile(
        self,
        db: Session,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> None:
        """Rebuild the Redis state from the durable log for one
        (workspace, tool, period) key. MUST be called before any
        ``reserve()`` accepts requests for that key after a Redis
        flush or cold worker start.

        Order:
        1. Read committed from ``llm_attempt_receipts`` (authoritative
           per-attempt cost post-cutover) for the current period → SET
           committed key.
        2. Read open ``budget_reservations`` rows → SET reserved
           counter + populate res_hash
        3. SET ready flag

        Concurrent reconcile calls for the same key overwrite each
        other; the last one wins but they compute the same value from
        the same durable source, so this is safe.

        P1-1 (#2209 PR 4): pre-cutover this summed
        ``guard_audit_events.cost_usd_after`` which used legacy audit-side
        math (no cache breakout). Live settlement uses the new engine's
        ``calculated_cost_microdollars`` on ``llm_attempt_receipts``. Reading
        from the audit table here made a Redis rebuild restore a DIFFERENT
        total than the live counter.

        P1-B (post-review): filter by ``usage_completeness='complete'``
        AND ``pricing_completeness in {'priced','override_applied'}``.
        A PARTIAL receipt CAN carry a non-null cost (the normalizer
        emits a number for the frames it saw), but the settlement path
        returns None → the reservation for that request STAYS OPEN.
        If Redis rebuild sums that non-null cost AND also sums the open
        reservation, we double-count. Only "definitively settleable"
        receipts contribute to the committed counter.

        P1-C (post-review): pre-cutover requests only exist in
        ``guard_audit_events`` (no receipts were being written when they
        settled). Add a fallback sum over audit rows whose request_id
        has NO settleable receipt — their ``cost_usd_after`` is the
        authoritative number the ledger already committed at settle
        time. This preserves the current period's historical balance
        without keeping the old engine on the live path."""
        period = monthly_period_key()
        period_start = _period_start(period)

        # 1) Committed from receipts (authoritative post-cutover source).
        from app.models.llm_attempt_receipt import LlmAttemptReceipt
        from app.modules.guard.models import BudgetReservation, GuardAuditEvent
        try:
            ws_uuid = uuid.UUID(workspace_id) if _looks_like_uuid(workspace_id) else workspace_id
        except (ValueError, AttributeError):
            ws_uuid = workspace_id

        from sqlalchemy.orm import aliased

        from app.runtime.accounting.settlement import definitive_receipt_clause

        # P1-B + #2410: only requests whose EVERY attempt is definitive
        # count as committed (the live/sweep all-or-nothing rule). A
        # request with any partial/unpriced attempt still has an open
        # reservation; counting its priced attempts too would double-charge.
        sibling = aliased(LlmAttemptReceipt)
        q = db.query(
            func.coalesce(func.sum(LlmAttemptReceipt.calculated_cost_microdollars), 0)
        ).filter(
            LlmAttemptReceipt.workspace_id == ws_uuid,
            LlmAttemptReceipt.finalized_at >= period_start,
            definitive_receipt_clause(LlmAttemptReceipt),
            ~db.query(sibling.request_id).filter(
                sibling.request_id == LlmAttemptReceipt.request_id,
                ~definitive_receipt_clause(sibling),
            ).exists(),
        )
        if ai_tool is not None:
            # R11 fix (reviewer P1) — carries over: transport-scoped
            # budget aggregates every receipt routed through that surface;
            # client-tool budget filters by ``client_tool``. Same column
            # semantics as ``GuardAuditEvent.source`` / ``ai_tool``.
            if _is_transport(ai_tool):
                q = q.filter(LlmAttemptReceipt.source == ai_tool)
            else:
                q = q.filter(LlmAttemptReceipt.client_tool == ai_tool)
        # Fix 1 (P1 #1) carries over: scope by identity when the budget
        # is user- or agent-scoped. ``developer_external_id`` is the
        # Clerk ID (text); ``agent_identity_id`` is the UUID FK.
        if clerk_user_id is not None:
            q = q.filter(LlmAttemptReceipt.developer_external_id == clerk_user_id)
        if agent_identity_id is not None:
            q = q.filter(LlmAttemptReceipt.agent_identity_id == agent_identity_id)
        committed_micros = int(q.scalar() or 0)

        # 1b) P1-C legacy fallback: audit rows whose request_id has NO
        # receipt AT ALL. Post-review fix: was ``no settleable receipt``,
        # which meant a post-cutover request with a PARTIAL / UNPRICED
        # receipt would fall back to its legacy audit cost — double-
        # counting the excluded partial and reintroducing the inaccurate
        # number the completeness gate was there to exclude. The
        # correct semantic is "genuinely pre-cutover" = no receipt at
        # all. Requests with non-settleable receipts stay unresolved
        # until the reconciler backfills a definitive one.
        legacy_q = db.query(
            func.coalesce(
                func.sum(GuardAuditEvent.cost_usd_after), 0.0
            )
        ).filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.cost_usd_after.isnot(None), GuardAuditEvent.budget_eligible(),
            ~db.query(LlmAttemptReceipt.request_id)
            .filter(
                LlmAttemptReceipt.request_id == GuardAuditEvent.request_id,
            )
            .exists(),
        )
        if ai_tool is not None:
            if _is_transport(ai_tool):
                legacy_q = legacy_q.filter(GuardAuditEvent.source == ai_tool)
            else:
                legacy_q = legacy_q.filter(GuardAuditEvent.ai_tool == ai_tool)
        if clerk_user_id is not None:
            legacy_q = legacy_q.filter(GuardAuditEvent.clerk_user_id == clerk_user_id)
        if agent_identity_id is not None:
            legacy_q = legacy_q.filter(
                GuardAuditEvent.agent_identity_id == agent_identity_id
            )
        legacy_usd = float(legacy_q.scalar() or 0.0)
        committed_micros += int(round(legacy_usd * 1_000_000))
        committed_cents = committed_micros // 10_000  # for legacy log lines

        # 2) Open reservations from durable log.
        open_rows = db.query(BudgetReservation).filter(
            BudgetReservation.workspace_id == ws_uuid,
            BudgetReservation.period_key == period,
            BudgetReservation.status == "open",
        )
        if ai_tool is None:
            open_rows = open_rows.filter(BudgetReservation.ai_tool.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.ai_tool == ai_tool)
        # Fix 1 (P1 #1): exact-scope match on reservation rows since
        # each budget owns only its own reservations under scope-aware
        # keying.
        if clerk_user_id is None:
            open_rows = open_rows.filter(BudgetReservation.clerk_user_id.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.clerk_user_id == clerk_user_id)
        if agent_identity_id is None:
            open_rows = open_rows.filter(BudgetReservation.agent_identity_id.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.agent_identity_id == agent_identity_id)

        reserved_total = 0
        hash_payload: dict[str, int] = {}
        for row in open_rows.all():
            # R9: prefer estimated_micros so partial cents are preserved.
            _row_micros = (
                row.estimated_micros
                if row.estimated_micros is not None
                else int(row.estimated_cents) * _MICROS_PER_CENT
            )
            hash_payload[str(row.id).replace("-", "")] = _row_micros
            reserved_total += _row_micros

        # 3) Write to Redis atomically.
        ttl = _seconds_until_next_period()
        client = self._client()
        pipe = client.pipeline()
        _sk = _scope_keys(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        pipe.set(_sk["committed"], committed_micros, ex=ttl)
        pipe.delete(_sk["reserved"])
        pipe.delete(_sk["res_hash"])
        if reserved_total > 0:
            pipe.set(_sk["reserved"], reserved_total, ex=ttl)
        if hash_payload:
            pipe.hset(_sk["res_hash"], mapping=hash_payload)
            pipe.expire(_sk["res_hash"], ttl)
        pipe.set(_sk["ready"], "1", ex=ttl)
        pipe.execute()
