"""Real-DB integration for Redis interruption scenarios (#2209 PR 2).

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.

Locks the contract that Redis outages MUST NOT prevent shadow receipts
from landing. The shadow writer only touches Postgres; adjacent
subsystems (budget ledger, rate limiter) that hit Redis can fail
independently without dragging accounting down.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


@pytest.fixture(scope="module")
def workspace_id() -> str:
    """Seed a workspace so the FK on llm_attempt_receipts is satisfied."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"redis-int-{ws_id[:8]}", "owner": "test-realdb"},
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
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()


def _receipt_exists(request_id: uuid.UUID) -> bool:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        return bool(
            db.execute(
                text(
                    "SELECT 1 FROM llm_attempt_receipts "
                    "WHERE request_id = :r LIMIT 1"
                ),
                {"r": str(request_id)},
            ).first()
        )


def test_shadow_write_succeeds_when_redis_client_import_fails(
    monkeypatch, workspace_id
):
    """Force any ``import redis`` at call time to raise. shadow_write does
    not use Redis directly — the receipt MUST still land in Postgres."""
    from app.runtime.accounting.shadow_writer import shadow_write

    # Sabotage the redis import so any accidental Redis dependency
    # surfaces as an ImportError instead of a hang.
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def _broken_import(name, *args, **kwargs):
        if name == "redis" or name.startswith("redis."):
            raise ImportError("redis package intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", _broken_import)

    req_id = uuid.uuid4()
    rid = shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        legacy_input_tokens=100,
        legacy_output_tokens=50,
        legacy_cost_usd=0.001,
    )
    assert rid is not None
    assert _receipt_exists(req_id)


def test_shadow_write_survives_redis_connect_timeout(monkeypatch, workspace_id):
    """Simulate a Redis TCP connect timeout during the request path. The
    shadow write path must complete regardless. Verifies that no
    accounting code path added a hidden Redis dependency along the way."""
    import socket

    from app.runtime.accounting.shadow_writer import shadow_write

    real_connect = socket.socket.connect

    def _fail_localhost_6379(self, address):
        host_port = address if isinstance(address, tuple) else (None, None)
        if host_port and str(host_port[0]) in {"127.0.0.1", "localhost"} and host_port[1] == 6379:
            raise TimeoutError("simulated Redis connect timeout")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", _fail_localhost_6379)

    req_id = uuid.uuid4()
    rid = shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )
    assert rid is not None
    assert _receipt_exists(req_id)
