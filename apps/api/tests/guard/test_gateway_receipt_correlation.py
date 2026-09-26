"""Accounting correlation must not depend on the durable-audit rollout."""
import asyncio
import time
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import BackgroundTasks, FastAPI
from fastapi.testclient import TestClient
from starlette.responses import StreamingResponse

from app.modules.guard import gateway_lifecycle
from app.modules.guard.gateway_handler import _wrap_stream_receipts
from app.modules.guard.routers import gateway_proxy


def open_row():
    return gateway_lifecycle.open_durable_row(
        workspace_id=str(uuid4()), clerk_user_id="user", ai_tool="codex", provider="openai",
        model="test", body={}, prompt_summary="", user_email=None, agent_identity_id=None,
        route="/gateway/v1/openai/v1/responses", hook_session_id=None, routing_meta={},
        conductai_run_id=None, conductai_workflow=None, conductai_workflow_id=None,
        request_correlation_id="untrusted-client-id",
    )


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["off", "fail_open"])
async def test_request_id_survives_audit_off_and_fail_open(monkeypatch, mode):
    monkeypatch.setattr(gateway_lifecycle.settings, "guard_use_durable_audit", mode != "off")
    monkeypatch.setattr(gateway_lifecycle.settings, "guard_durable_audit_rollout_pct", 100)
    monkeypatch.setattr(gateway_lifecycle.settings, "guard_durable_audit_fail_closed", False)
    insert = Mock(side_effect=RuntimeError("DB unavailable"))
    monkeypatch.setattr(gateway_lifecycle, "insert_accepted", insert)
    first, second = await open_row(), await open_row()
    assert UUID(first.request_id).version == 4
    assert first.request_id != second.request_id
    assert first.row_id is None and first.fail_response is None
    if mode == "off":
        insert.assert_not_called()


def test_single_phase_audit_receives_same_request_id():
    from app.guard.router import _schedule_audit
    request_id = str(uuid4())
    args = (str(uuid4()), "user", "codex", "openai", "test", "allowed", None,
            time.monotonic(), {}, "", None, None, None, None, None, {}, None,
            "/gateway/v1/openai/v1/responses", None, request_id)
    background = BackgroundTasks()
    _schedule_audit(background, args, response_bytes=b"{}", upstream=None)
    assert background.tasks[0].kwargs["request_id"] == request_id


@pytest.mark.anyio
@pytest.mark.parametrize("interrupted", [False, True])
async def test_stream_receipt_keeps_request_id_and_partial_bytes(monkeypatch, interrupted):
    written = []
    def write(**kwargs):
        written.append(kwargs)
        return [uuid4()]
    monkeypatch.setattr("app.runtime.accounting.shadow_writer.write_receipts_for_attempts", write)
    async def upstream():
        yield b'data: {"usage":{"output_tokens":1}}\n\n'
        if interrupted:
            raise asyncio.CancelledError()
    request_id = str(uuid4())
    response = _wrap_stream_receipts(StreamingResponse(upstream()), request_id=request_id)
    if interrupted:
        with pytest.raises(asyncio.CancelledError):
            async for _ in response.body_iterator:
                pass
    else:
        async for _ in response.body_iterator:
            pass
    assert len(written) == 1
    assert written[0]["request_id"] == request_id
    assert b'"output_tokens":1' in written[0]["response_bytes"]
    assert written[0]["winner_execution_outcome"] == ("disconnected" if interrupted else "succeeded")


def test_single_phase_writer_persists_request_correlation(monkeypatch):
    from app.guard import audit
    db = Mock()
    monkeypatch.setattr(audit, "SessionLocal", lambda: db)
    monkeypatch.setattr(audit, "set_workspace_rls", lambda *args: None)
    monkeypatch.setattr(audit, "_audit_tokens_and_cost", lambda **kwargs: (1, 2, 0.01))
    request_id = str(uuid4())
    audit.record(str(uuid4()), "user", "codex", "openai", "test", "allowed", None, 1,
                 body={}, response_bytes=b"{}", agent_identity_id=str(uuid4()), request_id=request_id)
    statement, params = db.execute.call_args.args
    assert "CAST(:request_id AS uuid)" in str(statement)
    assert params["request_id"] == request_id
    db.commit.assert_called_once()


def test_stream_outcome_does_not_overwrite_earlier_failed_attempt(monkeypatch):
    from app.runtime.accounting import shadow_writer
    written = []
    def write(**kwargs):
        written.append(kwargs)
        return uuid4()
    monkeypatch.setattr(shadow_writer, "shadow_write", write)
    shadow_writer.write_receipts_for_attempts(
        workspace_id=str(uuid4()), request_id=str(uuid4()), provider="openai", model="test",
        operation="/v1/responses", dispatched=True, response_bytes=b"{}",
        attempts_meta=[{"succeeded": False}, {"succeeded": True}],
        winner_execution_outcome="disconnected",
    )
    assert [r["execution_outcome"] for r in written] == ["failed", "disconnected"]


@pytest.mark.anyio
async def test_closing_stream_closes_original_and_writes_receipt(monkeypatch):
    closed, written = [], []
    async def upstream():
        try:
            yield b"partial"
            yield b"later"
        finally:
            closed.append(True)
    monkeypatch.setattr("app.runtime.accounting.shadow_writer.write_receipts_for_attempts",
                        lambda **kwargs: written.append(kwargs))
    response = _wrap_stream_receipts(StreamingResponse(upstream()), request_id=str(uuid4()))
    assert await response.body_iterator.__anext__() == b"partial"
    await response.body_iterator.aclose()
    assert closed == [True]
    assert written[0]["winner_execution_outcome"] == "disconnected"


@pytest.mark.parametrize("token,status", [(None, 401), ("expired", 401), ("guard-mt-valid", 200)])
def test_openai_catalog_uses_same_gateway_credentials(monkeypatch, token, status):
    app = FastAPI()
    app.include_router(gateway_proxy.router)
    app.dependency_overrides[gateway_proxy.get_db] = lambda: object()
    monkeypatch.setattr(gateway_proxy, "resolve_agent_token", lambda t, db: ("ws", "user") if t == "guard-mt-valid" else None)
    monkeypatch.setattr(gateway_proxy, "token_is_expired", lambda t, db: t == "expired")
    monkeypatch.setattr(gateway_proxy, "set_workspace_rls", lambda *args: None)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = TestClient(app).get("/gateway/v1/openai/v1/models", headers=headers)
    assert result.status_code == status
    if status == 200:
        assert result.json() == {"models": []}
    elif token == "expired":
        assert result.json()["detail"] == "Gateway credential expired"
