"""#2410 — the three settlement surfaces agree on a multi-attempt request.

Surfaces:
1. Live write: ``settle_micros_for_attempts`` (gateway). All-or-nothing:
   every attempt priced → commit the SUM; any unknown cost → None
   (reservation left open, PENDING_RECONCILER).
2. Redis rebuild: ``BudgetLedger.reconcile`` sums receipts into the
   committed counter and open reservations into the reserved counter.
3. Stale-reservation recovery: ``run_recovery_sweep``.

The sweep tests use a session double; the rebuild tests run the real
``reconcile()`` SQL against in-memory SQLite (tables copied from the ORM
with PG-only types swapped) so the aggregation is executed, not mocked.
"""
from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import fakeredis
import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session

_DEFINITIVE = ("priced", "override_applied")


def _chat_bytes(prompt: int, completion: int) -> bytes:
    return json.dumps({
        "id": "x", "object": "chat.completion", "model": "gpt-4o",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": prompt, "completion_tokens": completion,
                  "total_tokens": prompt + completion},
    }).encode()


def _receipt(request_id, ordinal, micros, *, usage="complete", pricing="priced"):
    return SimpleNamespace(
        request_id=request_id, attempt_ordinal=ordinal,
        calculated_cost_microdollars=micros,
        usage_completeness=usage, pricing_completeness=pricing,
    )


def _reservation(request_id, *, estimated_cents=500):
    return SimpleNamespace(
        id=uuid.uuid4(), workspace_id=uuid.uuid4(), clerk_user_id=None,
        agent_identity_id=None, ai_tool=None, period_key=_period(),
        status="open", request_id=request_id, estimated_cents=estimated_cents,
        estimated_micros=estimated_cents * 10_000,
        created_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


def _period() -> str:
    from app.core.budget_ledger import monthly_period_key
    return monthly_period_key()


class _SweepDB:
    """Session double for the sweep. ``filter()`` expressions are not
    evaluated, so the double answers the way the SQL would:
    - BudgetReservation: only rows still ``open`` (the sweep's filter).
    - LlmAttemptReceipt ``.all()``: every receipt for the request.
      ``.first()``: the first DEFINITIVE receipt — what the pre-#2410
      definitive-filtered ``.first()`` query returned.
    """

    def __init__(self, reservations, receipts, audit=None):
        self.reservations = reservations
        self.receipts = receipts
        self.audit = audit

    def query(self, model, *args):
        name = getattr(model, "__name__", "")
        chain = MagicMock()
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        if name == "BudgetReservation":
            chain.limit.return_value.all.side_effect = lambda: [
                r for r in self.reservations if r.status == "open"]
        elif name == "LlmAttemptReceipt":
            chain.all.return_value = list(self.receipts)
            chain.first.return_value = next(
                (r for r in self.receipts
                 if r.calculated_cost_microdollars is not None
                 and r.usage_completeness == "complete"
                 and r.pricing_completeness in _DEFINITIVE), None)
        else:
            chain.first.return_value = self.audit
        return chain

    def get(self, _model, pk):
        return next((r for r in self.reservations if r.id == pk), None)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def _sweep(db, ledger):
    from app.core import budget_reconciler as br
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger._allowlisted_workspaces", return_value=None), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=ledger):
        return br.run_recovery_sweep(session_factory=lambda: db, stale_seconds=1)


# ── Surface 3: recovery sweep ──────────────────────────────────────


def test_sweep_commits_sum_of_priced_attempts():
    rid = uuid.uuid4()
    res = _reservation(rid)
    db = _SweepDB([res], [_receipt(rid, 0, 300_000), _receipt(rid, 1, 700_000)])
    ledger = MagicMock()
    out = _sweep(db, ledger)
    assert out["committed"] == 1
    ledger.commit.assert_called_once()
    assert ledger.commit.call_args.kwargs["actual_micros"] == 1_000_000
    assert ledger.commit.call_args.kwargs["actual_cents"] == 100


def test_sweep_leaves_open_when_any_attempt_is_unpriced():
    """Live rule (#2209 / #2403 item 3): an attempt with unknown cost means
    the winner alone is a lower bound. Do not commit it; leave open."""
    rid = uuid.uuid4()
    res = _reservation(rid)
    db = _SweepDB(
        [res],
        [_receipt(rid, 0, None, usage="unavailable", pricing="unpriced"),
         _receipt(rid, 1, 700_000)],
        audit=SimpleNamespace(request_id=rid, lifecycle_state="finalized"),
    )
    ledger = MagicMock()
    out = _sweep(db, ledger)
    assert out["left_open"] == 1 and out["committed"] == 0
    ledger.commit.assert_not_called()
    ledger.release.assert_not_called()


def test_sweep_single_attempt_unchanged():
    rid = uuid.uuid4()
    db = _SweepDB([_reservation(rid)], [_receipt(rid, 0, 1_050_000)])
    ledger = MagicMock()
    out = _sweep(db, ledger)
    assert out["committed"] == 1
    assert ledger.commit.call_args.kwargs["actual_micros"] == 1_050_000


def test_sweep_twice_commits_once_and_moves_redis():
    """Real ledger on fakeredis. The first sweep moves the reservation from
    reserved → committed in Redis with the SUM; the second is a no-op."""
    from app.core.budget_ledger import BudgetLedger, _scope_keys, _seconds_until_next_period

    redis = fakeredis.FakeRedis(decode_responses=True)
    ledger = BudgetLedger(redis_client=redis)
    rid = uuid.uuid4()
    res = _reservation(rid, estimated_cents=500)
    keys = _scope_keys(str(res.workspace_id), None, None, None, res.period_key)
    # Same shape ``reserve()`` writes: hash keyed by the reservation's hex id.
    redis.hset(keys["res_hash"], res.id.hex, res.estimated_micros)
    redis.set(keys["reserved"], res.estimated_micros, ex=_seconds_until_next_period())
    db = _SweepDB([res], [_receipt(rid, 0, 300_000), _receipt(rid, 1, 700_000)])

    first = _sweep(db, ledger)
    second = _sweep(db, ledger)

    assert first["committed"] == 1 and second["committed"] == 0
    assert res.status == "committed" and res.actual_micros == 1_000_000
    assert int(redis.get(keys["committed"]) or 0) == 1_000_000
    assert redis.get(keys["reserved"]) is None
    assert redis.hlen(keys["res_hash"]) == 0


# ── Surface 2: Redis rebuild (real SQL on SQLite) ──────────────────


def _sqlite_copy(table: sa.Table, md: sa.MetaData) -> sa.Table:
    cols = [sa.Column(c.name, sa.JSON() if isinstance(c.type, JSONB) else c.type,
                      primary_key=c.primary_key)
            for c in table.columns]
    return sa.Table(table.name, md, *cols)


@pytest.fixture
def sqlite_db():
    from app.models.llm_attempt_receipt import LlmAttemptReceipt
    from app.modules.guard.models import BudgetReservation, GuardAuditEvent

    engine = sa.create_engine("sqlite://")
    md = sa.MetaData()
    for model in (LlmAttemptReceipt, BudgetReservation, GuardAuditEvent):
        _sqlite_copy(model.__table__, md)
    md.create_all(engine)
    with Session(engine) as db:
        yield db


def _insert_receipt(db, ws, rid, ordinal, micros, *, usage="complete", pricing="priced"):
    from app.models.llm_attempt_receipt import LlmAttemptReceipt
    db.execute(sa.insert(LlmAttemptReceipt.__table__).values(
        id=uuid.uuid4(), workspace_id=ws, request_id=rid, attempt_ordinal=ordinal,
        contract_version=1, provider="openai", model="gpt-4o", operation="chat",
        execution_outcome="succeeded", usage_origin="provider",
        usage_completeness=usage, pricing_completeness=pricing,
        calculated_cost_microdollars=micros, currency="USD",
        finalized_at=datetime.now(timezone.utc),
    ))


def _insert_open_reservation(db, ws, rid, estimated_micros):
    from app.modules.guard.models import BudgetReservation
    db.execute(sa.insert(BudgetReservation.__table__).values(
        id=uuid.uuid4(), workspace_id=ws, ai_tool=None, period_key=_period(),
        request_id=rid, estimated_cents=estimated_micros // 10_000,
        estimated_micros=estimated_micros, status="open",
        created_at=datetime.now(timezone.utc),
    ))


def _rebuild(db, ws) -> tuple[int, int]:
    from app.core.budget_ledger import BudgetLedger, _scope_keys
    redis = fakeredis.FakeRedis(decode_responses=True)
    BudgetLedger(redis_client=redis).reconcile(db, str(ws), None)
    keys = _scope_keys(str(ws), None, None, None, _period())
    return int(redis.get(keys["committed"]) or 0), int(redis.get(keys["reserved"]) or 0)


def test_rebuild_sums_every_priced_attempt(sqlite_db):
    ws, rid = uuid.uuid4(), uuid.uuid4()
    _insert_receipt(sqlite_db, ws, rid, 0, 300_000)
    _insert_receipt(sqlite_db, ws, rid, 1, 700_000)
    assert _rebuild(sqlite_db, ws) == (1_000_000, 0)


def test_rebuild_does_not_count_winner_of_request_with_unpriced_attempt(sqlite_db):
    """The live path and the sweep leave this reservation open, so the
    rebuild counts its estimate as reserved. Counting the priced winner as
    committed too would charge the request twice."""
    ws, rid = uuid.uuid4(), uuid.uuid4()
    _insert_receipt(sqlite_db, ws, rid, 0, None, usage="unavailable", pricing="unpriced")
    _insert_receipt(sqlite_db, ws, rid, 1, 700_000)
    _insert_open_reservation(sqlite_db, ws, rid, 5_000_000)
    # An unrelated fully-priced request still counts.
    _insert_receipt(sqlite_db, ws, uuid.uuid4(), 0, 250_000)
    assert _rebuild(sqlite_db, ws) == (250_000, 5_000_000)


# ── All three agree ────────────────────────────────────────────────


def test_live_sweep_and_rebuild_agree_on_multi_attempt_amount(sqlite_db):
    from app.runtime.accounting.settlement import (
        compute_settlement_micros, settle_micros_for_attempts,
    )

    failed, winner = _chat_bytes(4_000, 0), _chat_bytes(1_000, 500)
    attempts = [
        {"provider_or_integration": "openai", "model": "gpt-4o", "succeeded": False,
         "response_bytes_b64": base64.b64encode(failed).decode()},
        {"provider_or_integration": "openai", "model": "gpt-4o-mini", "succeeded": True},
    ]
    live = settle_micros_for_attempts(
        attempts_meta=attempts, request_provider="openai", request_model="gpt-4o",
        operation="openai_chat_completions", winner_response_bytes=winner)
    per_attempt = [
        compute_settlement_micros(provider="openai", model=m, operation="openai_chat_completions",
                                  response_bytes=b)
        for m, b in (("gpt-4o", failed), ("gpt-4o-mini", winner))
    ]
    assert live is not None and None not in per_attempt and live == sum(per_attempt)

    rid = uuid.uuid4()
    ledger = MagicMock()
    _sweep(_SweepDB([_reservation(rid)],
                    [_receipt(rid, i, m) for i, m in enumerate(per_attempt)]), ledger)
    swept = ledger.commit.call_args.kwargs["actual_micros"]

    ws = uuid.uuid4()
    for i, m in enumerate(per_attempt):
        _insert_receipt(sqlite_db, ws, rid, i, m)
    rebuilt, _ = _rebuild(sqlite_db, ws)

    assert live == swept == rebuilt
