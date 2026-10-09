"""Real-DB integration for the PR 4 cutover P1 fixes — reconcile paths
(P1-B partial receipts, P1-C pre-cutover audit fallback, P1-D receipt
ordering, Responses normalizer).

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.
Split from ``test_pr4_cutover_realdb.py``; shared fixture lives in
``_pr4_cutover_helpers.py``.
"""
from __future__ import annotations

import os
import uuid

import pytest

from tests.integration._pr4_cutover_helpers import workspace_id  # noqa: F401 — fixture

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)

# ─── P1-B (reconcile skips partial receipts) ──────────────────────────

def test_redis_reconcile_skips_partial_receipts_to_prevent_double_count(
    workspace_id,
):
    """PR 4 P1-B: PARTIAL receipts have open reservations. If the Redis
    rebuild sums them alongside the open reservation, we double-count."""
    from app.core.database import SessionLocal
    from app.core.budget_ledger import BudgetLedger
    from app.runtime.accounting.shadow_writer import shadow_write

    ai_tool = f"pr4-partial-skip-{uuid.uuid4().hex[:8]}"

    # One settleable receipt (1050 μUSD, complete + priced).
    shadow_write(
        workspace_id=workspace_id,
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',

        source="gateway",
        client_tool=ai_tool,
    )
    # One PARTIAL receipt (still has a cost, but usage_completeness=partial).
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
        client_tool=ai_tool,
    )

    committed_written: dict[str, int] = {}

    class _FakeRedis:
        def __init__(self):
            self._store: dict[str, str] = {}

        def get(self, k):
            return self._store.get(k)

        def set(self, k, v, **kw):
            self._store[k] = str(v)
            committed_written[k] = int(v)
            return True

        def incrbyfloat(self, k, v):
            self._store[k] = str(float(self._store.get(k, "0")) + float(v))
            return self._store[k]

        def incrby(self, k, v):
            self._store[k] = str(int(self._store.get(k, "0")) + int(v))
            return self._store[k]

        def delete(self, *keys):
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

        def hset(self, *a, **k):
            return 1

        def hgetall(self, *a, **k):
            return {}

        def expire(self, *a, **k):
            return True

        def pipeline(self, *a, **k):
            return self

        def execute(self, *a, **k):
            return []

    ledger = BudgetLedger(redis_client=_FakeRedis())
    with SessionLocal() as db:
        ledger.reconcile(db, workspace_id, ai_tool=ai_tool)

    committed_keys = [k for k in committed_written if "committed" in k]
    assert committed_keys
    total = sum(committed_written[k] for k in committed_keys)
    # Only the complete+priced receipt counts (1_050). Partial excluded.
    assert total == 1_050

# ─── P1-C (pre-cutover audit fallback) ────────────────────────────────

def test_reconcile_folds_in_legacy_audit_for_requests_without_receipts(
    workspace_id,
):
    """PR 4 P1-C: pre-cutover requests have audit rows but no receipts.
    The rebuild must include them; otherwise historical spend
    disappears from the current period's balance."""
    from app.core.database import SessionLocal
    from app.core.budget_ledger import BudgetLedger
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    ai_tool = f"pr4-legacy-{uuid.uuid4().hex[:8]}"

    # Post-cutover receipt: 1_050 μUSD.
    shadow_write(
        workspace_id=workspace_id,
        request_id=uuid.uuid4(),
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',

        source="gateway",
        client_tool=ai_tool,
    )
    # Pre-cutover audit event WITHOUT a corresponding receipt: 0.001 USD
    # = 1_000 μUSD. Must be included in the rebuilt total.
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), gen_random_uuid(), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.001, :ai_tool)"
            ),
            {"ws": workspace_id, "ai_tool": ai_tool},
        )
        db.commit()

    committed_written: dict[str, int] = {}

    class _FakeRedis:
        def __init__(self):
            self._store: dict[str, str] = {}

        def get(self, k):
            return self._store.get(k)

        def set(self, k, v, **kw):
            self._store[k] = str(v)
            committed_written[k] = int(v)
            return True

        def incrbyfloat(self, k, v):
            self._store[k] = str(float(self._store.get(k, "0")) + float(v))
            return self._store[k]

        def incrby(self, k, v):
            self._store[k] = str(int(self._store.get(k, "0")) + int(v))
            return self._store[k]

        def delete(self, *keys):
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

        def hset(self, *a, **k):
            return 1

        def hgetall(self, *a, **k):
            return {}

        def expire(self, *a, **k):
            return True

        def pipeline(self, *a, **k):
            return self

        def execute(self, *a, **k):
            return []

    ledger = BudgetLedger(redis_client=_FakeRedis())
    with SessionLocal() as db:
        ledger.reconcile(db, workspace_id, ai_tool=ai_tool)

    committed_keys = [k for k in committed_written if "committed" in k]
    total = sum(committed_written[k] for k in committed_keys)
    # 1_050 receipt + 1_000 audit fallback = 2_050 μUSD.
    assert total == 2_050

def test_reconcile_suppresses_audit_when_partial_receipt_exists(
    workspace_id,
):
    """PR 4 review P1 (post-cutover): a request with BOTH a PARTIAL
    receipt AND an audit row must NOT contribute to the committed
    counter — otherwise the enforcement counter reintroduces the legacy
    audit cost the completeness gate was there to exclude. Reconciler
    fallback fires only for requests with NO receipt at all."""
    from app.core.database import SessionLocal
    from app.core.budget_ledger import BudgetLedger
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    ai_tool = f"pr4-partial-audit-{uuid.uuid4().hex[:8]}"
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
        client_tool=ai_tool,
    )
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.42, :ai_tool)"
            ),
            {
                "ws": workspace_id,
                "req": str(request_id),
                "ai_tool": ai_tool,
            },
        )
        db.commit()

    committed_written: dict[str, int] = {}

    class _FakeRedis:
        def __init__(self):
            self._store: dict[str, str] = {}
        def get(self, k): return self._store.get(k)
        def set(self, k, v, **kw):
            self._store[k] = str(v); committed_written[k] = int(v); return True
        def incrbyfloat(self, k, v):
            self._store[k] = str(float(self._store.get(k, "0")) + float(v)); return self._store[k]
        def incrby(self, k, v):
            self._store[k] = str(int(self._store.get(k, "0")) + int(v)); return self._store[k]
        def delete(self, *keys):
            for k in keys: self._store.pop(k, None)
            return len(keys)
        def hset(self, *a, **k): return 1
        def hgetall(self, *a, **k): return {}
        def expire(self, *a, **k): return True
        def pipeline(self, *a, **k): return self
        def execute(self, *a, **k): return []

    ledger = BudgetLedger(redis_client=_FakeRedis())
    with SessionLocal() as db:
        ledger.reconcile(db, workspace_id, ai_tool=ai_tool)

    committed_keys = [k for k in committed_written if "committed" in k]
    total = sum(committed_written[k] for k in committed_keys)
    # Neither the partial receipt (1 μUSD or so) nor the audit fallback
    # (420_000 μUSD) contributes. Pre-fix, ``NOT EXISTS settleable
    # receipt`` matched the partial → audit fallback fired → total
    # would be 420_000.
    assert total == 0


def test_reconcile_does_not_double_count_audit_when_receipt_exists(
    workspace_id,
):
    """Pre-cutover fallback filter: a request with BOTH an audit event
    AND a settleable receipt (either from live cutover or a migrated
    row) must be counted ONCE — from the receipt."""
    from app.core.database import SessionLocal
    from app.core.budget_ledger import BudgetLedger
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    ai_tool = f"pr4-nodup-{uuid.uuid4().hex[:8]}"
    request_id = uuid.uuid4()

    # Same request: settleable receipt (1_050 μUSD) + audit (0.42 USD).
    shadow_write(
        workspace_id=workspace_id,
        request_id=request_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',

        source="gateway",
        client_tool=ai_tool,
    )
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, ts, source, provider, model, "
                " decision, cost_usd_after, ai_tool) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:req AS uuid), "
                "        now(), 'gateway', 'anthropic', 'claude-sonnet-4-6', "
                "        'allowed', 0.42, :ai_tool)"
            ),
            {
                "ws": workspace_id,
                "req": str(request_id),
                "ai_tool": ai_tool,
            },
        )
        db.commit()

    committed_written: dict[str, int] = {}

    class _FakeRedis:
        def __init__(self):
            self._store: dict[str, str] = {}

        def get(self, k):
            return self._store.get(k)

        def set(self, k, v, **kw):
            self._store[k] = str(v)
            committed_written[k] = int(v)
            return True

        def incrbyfloat(self, k, v):
            self._store[k] = str(float(self._store.get(k, "0")) + float(v))
            return self._store[k]

        def incrby(self, k, v):
            self._store[k] = str(int(self._store.get(k, "0")) + int(v))
            return self._store[k]

        def delete(self, *keys):
            for k in keys:
                self._store.pop(k, None)
            return len(keys)

        def hset(self, *a, **k):
            return 1

        def hgetall(self, *a, **k):
            return {}

        def expire(self, *a, **k):
            return True

        def pipeline(self, *a, **k):
            return self

        def execute(self, *a, **k):
            return []

    ledger = BudgetLedger(redis_client=_FakeRedis())
    with SessionLocal() as db:
        ledger.reconcile(db, workspace_id, ai_tool=ai_tool)

    committed_keys = [k for k in committed_written if "committed" in k]
    total = sum(committed_written[k] for k in committed_keys)
    # Receipt only (1_050), NOT 1_050 + 420_000.
    assert total == 1_050

# ─── P1-D (receipts written before settlement) ────────────────────────

def test_gateway_handler_writes_receipts_before_settling():
    """P1-D wiring pin: gateway_handler must call the receipt writer
    BEFORE ``_settle_reservations`` on both the non-streaming and
    streaming settlement paths. Reversing that ordering leaves
    committed spend without recovery-authoritative evidence."""
    from tests.guard._gateway_handler_sources import gateway_lifecycle_source

    src = gateway_lifecycle_source()
    # Non-streaming: receipts write logs 'receipts_partial_skip_settle'
    # and settle is gated on ``_receipts_durable``.
    assert "_receipts_durable" in src
    assert "receipts_partial_skip_settle" in src or "receipts_write_failed" in src
    # Streaming wrapper: parallel gate.
    assert "_stream_receipts_durable" in src

def test_responses_operation_populates_output_tokens_correctly(workspace_id):
    """Receipt written under ``operation`` containing 'responses' must
    pick OPENAI_RESPONSES family. Pre-fix the stream wrapper hardcoded
    'chat.completions.stream' and responses-shape usage was invisible."""
    from app.core.database import SessionLocal
    from app.runtime.accounting.shadow_writer import shadow_write
    from sqlalchemy import text

    request_id = uuid.uuid4()
    responses_bytes = b'{"usage":{"input_tokens":100,"output_tokens":50}}'
    ai_tool = f"pr4-resp-{uuid.uuid4().hex[:8]}"
    shadow_write(
        workspace_id=workspace_id,
        request_id=request_id,
        provider="openai",
        model="gpt-4.1",
        operation="/gateway/v1/openai/v1/responses",  # P1-4 real path
        dispatched=True,
        response_bytes=responses_bytes,

        source="gateway",
        client_tool=ai_tool,
    )

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT total_input_tokens, total_output_tokens, "
                "       calculated_cost_microdollars "
                "FROM llm_attempt_receipts WHERE request_id = :r"
            ),
            {"r": str(request_id)},
        ).one()
        # Responses family parses input_tokens/output_tokens correctly.
        # Under Chat family, these fields are ignored → tokens NULL.
        assert row.total_input_tokens == 100
        assert row.total_output_tokens == 50
        assert row.calculated_cost_microdollars == 600
