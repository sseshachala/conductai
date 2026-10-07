"""Shared fixture + receipt writer for the PR 4 cutover real-DB tests
(``test_pr4_cutover_realdb.py``, ``test_pr4_cutover_reconcile_realdb.py``).
"""
from __future__ import annotations

import uuid

import pytest

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
            {"id": ws_id, "name": f"pr4-{ws_id[:8]}", "owner": "test-realdb"},
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

def _insert_receipt(
    workspace_id: str,
    calculated_micros: int | None,
    *,
    ai_tool: str = "test",
    source: str = "gateway",
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
) -> uuid.UUID:
    from app.runtime.accounting.shadow_writer import shadow_write

    request_id = uuid.uuid4()
    body = (
        b'{"usage":{"input_tokens":100,"output_tokens":50}}'
        if calculated_micros is not None
        else None
    )
    result = shadow_write(
        workspace_id=workspace_id,
        request_id=request_id,
        provider=provider,
        model=model,
        operation="messages.create",
        dispatched=True,
        response_bytes=body,

        source=source,
        client_tool=ai_tool,
    )
    assert result is not None
    return request_id
