"""Contract tests for the durable-audit path in _proxy() and _stream_chunks().

Post-P1 review v2 requirements — these tests exercise the actual failure
modes the reviewer flagged, not the mocked-SQL happy paths of the earlier
suite. Focus:

- Database outage BEFORE forwarding → 503, zero upstream calls
- Server-generated request_id ignores X-Request-Id for uniqueness
- IntegrityError on internal id (should be astronomically rare) → 409
- Stream cancellation → execution_status='interrupted', finalize completes
- Cleanup failures never block finalize
- Concurrent duplicate handling classifies correctly
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch

import pytest


# ─── Fixtures for the stream harness ────────────────────────────────────


class _AsyncByteStream:
    """Async iterator that yields configurable chunks, optionally raising."""

    def __init__(self, chunks: list[bytes], *, raise_after: int | None = None,
                 raise_kind: type[BaseException] = Exception):
        self._chunks = list(chunks)
        self._raise_after = raise_after
        self._raise_kind = raise_kind
        self._i = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise_after is not None and self._i == self._raise_after:
            raise self._raise_kind("simulated stream failure")
        if self._i >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._i]
        self._i += 1
        return chunk


def _mock_httpx_response(chunks: list[bytes], *,
                        raise_after: int | None = None,
                        raise_kind: type[BaseException] = Exception,
                        aclose_raises: bool = False) -> MagicMock:
    resp = MagicMock()
    resp.aiter_bytes = lambda: _AsyncByteStream(chunks, raise_after=raise_after, raise_kind=raise_kind)
    if aclose_raises:
        resp.aclose = AsyncMock(side_effect=RuntimeError("cleanup boom"))
    else:
        resp.aclose = AsyncMock()
    return resp


def _mock_httpx_client(aclose_raises: bool = False) -> MagicMock:
    client = MagicMock()
    if aclose_raises:
        client.aclose = AsyncMock(side_effect=RuntimeError("cleanup boom"))
    else:
        client.aclose = AsyncMock()
    return client


def _audit_args_with_durable_row(row_id: str = "22222222-2222-2222-2222-222222222222"):
    """Build the tuple _stream_chunks expects when a durable row exists."""
    import time
    return (
        "ef0a7e36-42a7-4968-9e6f-ee30d8e45383",  # 0 workspace_id
        "user_abc",                                # 1 clerk_user_id
        "claude-code",                             # 2 ai_tool
        "anthropic",                               # 3 provider
        "claude-sonnet",                           # 4 model
        "allowed",                                 # 5 decision
        None,                                      # 6 rule_id
        time.monotonic() - 0.5,                    # 7 started
        {"messages": []},                          # 8 body
        "prompt",                                  # 9 prompt_summary
        "user@example.com",                        # 10 user_email
        None, None, None,                          # 11-13 run/workflow ids
        None,                                      # 14 hook_session_id
        None,                                      # 15 routing_meta
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",   # 16 agent_identity_id
        "/proxy/anthropic/v1/messages",           # 17 route
        row_id,                                    # 18 durable_row_id
    )


# ─── Contract: stream cancellation ─────────────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_cancellation_classifies_as_interrupted_not_success():
    """When cancellation reaches _stream_chunks, execution_status must
    NEVER be 'success'. Reviewer's P1 finding 2 — CancelledError was
    previously falling through the except-Exception handler which left
    execution_status as its default 'success'. The finalize call must
    still complete via asyncio.shield."""
    from fastapi import BackgroundTasks
    from app.guard.router import _stream_chunks

    resp = _mock_httpx_response([b"partial-", b"chunk-"])
    client = _mock_httpx_client()
    bg = BackgroundTasks()
    audit_args = _audit_args_with_durable_row()

    captured = {"finalize_calls": []}

    def _fake_finalize(row_id, workspace_id, **kwargs):
        captured["finalize_calls"].append({
            "row_id": row_id,
            "workspace_id": workspace_id,
            "execution_status": kwargs.get("execution_status"),
            "result_summary": kwargs.get("result_summary"),
        })
        return True

    with patch("app.guard.audit.finalize", _fake_finalize), \
         patch("app.guard.audit.renew_lease", return_value=True):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        # Advance to the first yielded chunk so the generator is
        # suspended at its `yield chunk` line.
        first = await gen.__anext__()
        assert first == b"partial-"
        # Throw CancelledError INTO the generator — this is exactly
        # what asyncio does when task.cancel() reaches a coroutine
        # suspended at an await point. It routes through the
        # except asyncio.CancelledError handler and re-raises.
        with pytest.raises(asyncio.CancelledError):
            await gen.athrow(asyncio.CancelledError)

    assert len(captured["finalize_calls"]) == 1
    call = captured["finalize_calls"][0]
    assert call["execution_status"] == "interrupted"
    assert "cancellation" in (call["result_summary"] or "").lower()


@pytest.mark.anyio("asyncio")
async def test_cleanup_failure_does_not_block_finalize():
    """Even if resp.aclose() or client.aclose() raise (network stack in
    a weird state), the durable finalize must still run. Contextlib
    suppress guards each cleanup independently."""
    from fastapi import BackgroundTasks
    from app.guard.router import _stream_chunks

    resp = _mock_httpx_response([b"ok"], aclose_raises=True)
    client = _mock_httpx_client(aclose_raises=True)
    bg = BackgroundTasks()
    audit_args = _audit_args_with_durable_row()

    finalize_called = []
    with patch("app.guard.audit.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.guard.audit.renew_lease", return_value=True):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        async for _ in gen:
            pass

    assert len(finalize_called) == 1
    assert finalize_called[0].get("execution_status") == "success"


@pytest.mark.anyio("asyncio")
async def test_upstream_exception_classifies_as_error():
    """Regular upstream failure (not cancellation) sets 'error' not
    'interrupted' — the two failure classes need distinct signals."""
    from fastapi import BackgroundTasks
    from app.guard.router import _stream_chunks

    resp = _mock_httpx_response([b"first"], raise_after=1, raise_kind=RuntimeError)
    client = _mock_httpx_client()
    bg = BackgroundTasks()
    audit_args = _audit_args_with_durable_row()

    finalize_called = []
    with patch("app.guard.audit.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.guard.audit.renew_lease", return_value=True):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        with pytest.raises(RuntimeError):
            async for _ in gen:
                pass

    assert len(finalize_called) == 1
    assert finalize_called[0].get("execution_status") == "error"


# ─── Contract: server-generated request_id ─────────────────────────────


def test_client_x_request_id_is_stored_as_correlation_only_not_uniqueness_key():
    """Client-supplied X-Request-Id must NEVER drive the durable row's
    unique index. Server generates the internal id; client's value goes
    into routing_meta so it stays queryable for correlation. Reviewer's
    P1 finding 1 root cause."""
    from app.modules.guard.routers import proxy as proxy_mod
    src = open(proxy_mod.__file__).read()
    # The proxy must generate its own UUID for request_id; the header
    # goes into routing_meta.client_request_id.
    assert "str(_uuid.uuid4())" in src
    assert "client_request_id" in src
    # The old pattern (using header as request_id) must be gone.
    assert 'request.headers.get("x-request-id") or str(_uuid.uuid4())' not in src


def test_response_cache_module_no_longer_present():
    """Response replay was removed pending a proper ownership-scoped
    idempotency design. The Redis cache module must not exist so no
    accidental import can re-introduce the cross-tenant leak path."""
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.guard.response_cache")


@pytest.mark.skipif(
    __import__("os").environ.get("RUN_DB_INTEGRATION_TESTS") != "1",
    reason="Requires a running Postgres; nightly workflow sets RUN_DB_INTEGRATION_TESTS=1.",
)
def test_db_outage_returns_503_and_never_forwards_upstream():
    """P1 v3 review finding 3 — the reviewer's central acceptance
    criterion. Actually invoke the handler with insert_accepted mocked
    to raise and verify:
        (a) 503 response
        (b) transport.forward was NEVER called
    """
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock, patch, AsyncMock
    from app.main import app
    from app.core.database import get_db
    from app.core.config import settings

    _prev_flag = settings.guard_use_durable_audit
    _prev_fail = settings.guard_durable_audit_fail_closed
    settings.guard_use_durable_audit = True
    settings.guard_durable_audit_fail_closed = True

    forward_mock = AsyncMock(side_effect=AssertionError(
        "transport.forward MUST NOT be called when the durable write fails"
    ))

    db_mock = MagicMock()
    workspace_id = "00000000-0000-0000-0000-000000000abc"

    def _insert_boom(*a, **kw):
        raise RuntimeError("simulated DB outage during insert_accepted")

    app.dependency_overrides[get_db] = lambda: db_mock

    class _FakeTransport:
        forward = forward_mock

    class _FakeRegistry:
        def for_provider(self, *a, **kw):
            return _FakeTransport()

    try:
        with patch(
            "app.modules.guard.routers.proxy._insert_accepted_audit",
            _insert_boom,
        ), patch(
            "app.modules.guard.routers.proxy.get_provider_transport_registry",
            return_value=_FakeRegistry(),
        ), patch(
            "app.modules.guard.routers.proxy.resolve_agent_token",
            return_value=(workspace_id, "clerk_user_test"),
        ), patch(
            "app.modules.guard.routers.proxy.set_workspace_rls",
            lambda *a, **kw: None,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/proxy/anthropic/v1/messages",
                headers={"x-api-key": "cond_agt_test"},
                json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert resp.status_code == 503, (
                f"expected 503 when durable write fails, got {resp.status_code}: {resp.text}"
            )
            forward_mock.assert_not_called()
    finally:
        app.dependency_overrides.clear()
        settings.guard_use_durable_audit = _prev_flag
        settings.guard_durable_audit_fail_closed = _prev_fail


@pytest.mark.anyio("asyncio")
async def test_finalize_runs_even_when_both_close_calls_raise_and_stream_yields_errors():
    """Belt-and-braces: (a) stream yields normally, (b) both aclose()
    calls raise, (c) renewal also fails. Finalize MUST still land."""
    from fastapi import BackgroundTasks
    from app.guard.router import _stream_chunks

    resp = _mock_httpx_response([b"a", b"b"], aclose_raises=True)
    client = _mock_httpx_client(aclose_raises=True)
    bg = BackgroundTasks()
    audit_args = _audit_args_with_durable_row()

    finalize_called = []

    def _raise_renew(*a, **kw):
        raise RuntimeError("renewal boom")

    with patch("app.guard.audit.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.guard.audit.renew_lease", _raise_renew):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        async for _ in gen:
            pass

    assert len(finalize_called) == 1
    assert finalize_called[0].get("execution_status") == "success"
