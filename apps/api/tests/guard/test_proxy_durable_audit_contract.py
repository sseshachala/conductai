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

    with patch("app.modules.guard.gateway_lifecycle.finalize", _fake_finalize), \
         patch("app.guard.audit.renew_lease", return_value=True), \
         patch("app.modules.guard.gateway_lifecycle.renew_lease", return_value=True):
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
    with patch("app.modules.guard.gateway_lifecycle.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.guard.audit.renew_lease", return_value=True), \
         patch("app.modules.guard.gateway_lifecycle.renew_lease", return_value=True):
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
    with patch("app.modules.guard.gateway_lifecycle.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.guard.audit.renew_lease", return_value=True), \
         patch("app.modules.guard.gateway_lifecycle.renew_lease", return_value=True):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        with pytest.raises(RuntimeError):
            async for _ in gen:
                pass

    assert len(finalize_called) == 1
    assert finalize_called[0].get("execution_status") == "error"


# ─── Contract: server-generated request_id ─────────────────────────────


@pytest.mark.anyio("asyncio")
async def test_client_x_request_id_is_stored_as_correlation_only_not_uniqueness_key():
    """Client-supplied X-Request-Id must NEVER drive the durable row's
    unique index. Behavior test — replaces the earlier source-text grep.

    Locks the invariant at the seam it matters at: the ``request_id``
    handed to ``insert_accepted`` MUST be a server-generated UUID4 and
    the client's header value MUST land in ``routing_meta.client_request_id``
    (correlation metadata only, never the uniqueness key)."""
    import uuid as _uuid_mod
    from app.modules.guard import gateway_lifecycle

    captured: dict = {}

    def _fake_insert(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "00000000-0000-0000-0000-000000000001"

    client_supplied = "client-picked-id-should-not-be-used-as-key"
    with patch("app.modules.guard.gateway_lifecycle.insert_accepted", _fake_insert), \
         patch("app.modules.guard.gateway_lifecycle.renew_lease", return_value=True), \
         patch.object(gateway_lifecycle.settings, "guard_use_durable_audit", True), \
         patch.object(gateway_lifecycle.settings, "guard_durable_audit_rollout_pct", 100), \
         patch.object(gateway_lifecycle.settings, "guard_durable_audit_stream_renew_seconds", 0):
        result = await gateway_lifecycle.open_durable_row(
            workspace_id="ef0a7e36-42a7-4968-9e6f-ee30d8e45383",
            clerk_user_id="user_abc",
            ai_tool="claude-code",
            provider="anthropic",
            model="claude-sonnet",
            body={"messages": []},
            prompt_summary="prompt",
            user_email=None,
            agent_identity_id=None,
            route="/gateway/v1/anthropic/v1/messages",
            hook_session_id=None,
            routing_meta={"tier_form": "cheap"},
            conductai_run_id=None,
            conductai_workflow=None,
            conductai_workflow_id=None,
            request_correlation_id=client_supplied,
        )

    assert result.fail_response is None, "durable row must open cleanly on happy path"
    assert result.row_id == "00000000-0000-0000-0000-000000000001"

    request_id = captured["kwargs"]["request_id"]
    assert request_id != client_supplied, (
        "server MUST NOT reuse the client X-Request-Id as the unique key"
    )
    # Server-generated request_id must be a valid UUID4.
    _uuid_mod.UUID(request_id, version=4)

    routing_meta = captured["kwargs"]["routing_meta"]
    assert routing_meta.get("client_request_id") == client_supplied, (
        "client X-Request-Id must be preserved in routing_meta as correlation only"
    )
    # Original routing_meta keys must survive (not clobbered by the merge).
    assert routing_meta.get("tier_form") == "cheap"


def test_response_cache_module_no_longer_present():
    """Response replay was removed pending a proper ownership-scoped
    idempotency design. The Redis cache module must not exist so no
    accidental import can re-introduce the cross-tenant leak path."""
    import importlib
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.guard.response_cache")


def test_db_outage_returns_503_and_never_forwards_upstream():
    """P1 v3 review finding 3 — the reviewer's central acceptance
    criterion. Actually invoke the handler with insert_accepted mocked
    to raise and verify all four invariants:

        (a) insert_accepted() was actually reached — an earlier 503
            (e.g. credentials-missing) would falsely pass without this.
        (b) transport.forward was NEVER called.
        (c) 503 response.
        (d) 503 body carries the audit-specific message so telemetry
            can distinguish this failure class from a plain vendor 503.

    Previously guarded behind RUN_DB_INTEGRATION_TESTS=1 which the
    nightly workflow never sets (it sets RUN_DURABLE_AUDIT_REALDB=1
    and runs a different file). SessionLocal is mocked here so no
    real Postgres is needed — the test is a unit test now.
    """
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock, patch, AsyncMock
    from app.main import app
    from app.core.database import get_db
    from app.core.config import settings

    _prev_flag = settings.guard_use_durable_audit
    _prev_fail = settings.guard_durable_audit_fail_closed
    _prev_pct  = settings.guard_durable_audit_rollout_pct
    settings.guard_use_durable_audit = True
    settings.guard_durable_audit_fail_closed = True
    # #1995 canary gate — force 100% so this test's synthetic
    # workspace is always in the durable path.
    settings.guard_durable_audit_rollout_pct = 100

    forward_mock = AsyncMock(side_effect=AssertionError(
        "transport.forward MUST NOT be called when the durable write fails"
    ))

    db_mock = MagicMock()
    workspace_id = "00000000-0000-0000-0000-000000000abc"

    insert_calls: list = []

    def _insert_boom(*a, **kw):
        insert_calls.append((a, kw))
        raise RuntimeError("simulated DB outage during insert_accepted")

    app.dependency_overrides[get_db] = lambda: db_mock

    class _FakeTransport:
        forward = forward_mock

    class _FakeRegistry:
        def for_provider(self, *a, **kw):
            return _FakeTransport()

    # A prompt-eval policy engine stub so the handler skips the block/
    # approval branches and reaches the vault + durable-audit steps
    # without needing DB-backed policy sources.
    from app.guard.policy_types import PolicyAction, PolicyDecision
    _allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="test")

    try:
        with patch(
            "app.modules.guard.gateway_lifecycle.insert_accepted",
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
        ), patch(
            "app.modules.guard.routers.proxy.SessionLocal",
            lambda: db_mock,
        ), patch(
            "app.guard.policy.evaluate_composed",
            lambda ctx: _allow_decision,
        ), patch(
            "app.modules.guard.routers.proxy._upstream_url",
            lambda db, ws, prov, env: "http://mock-upstream",
        ), patch(
            "app.modules.guard.routers.proxy._upstream_api_key",
            lambda db, ws, env: None,
        ), patch(
            "app.modules.guard.routers.proxy._vault_key",
            lambda db, ws, prov, env: "sk-fake",
        ), patch(
            "app.modules.guard.routers.proxy._flatten_prompt",
            lambda body: "hello",
        ), patch(
            "app.modules.guard.routers.proxy._estimate_input_tokens",
            lambda body: 10,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.post(
                "/proxy/anthropic/v1/messages",
                headers={"x-api-key": "cond_agt_test"},
                json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
            )
            # (a) insert_accepted MUST have been reached — otherwise the
            # 503 could be from any earlier failure and this test would
            # silently guard nothing.
            assert insert_calls, (
                "insert_accepted was never called — the request failed before "
                "reaching the durable-audit lifecycle, so this test does not "
                "actually cover the reviewer's failure mode."
            )
            # (b) upstream forward is fenced.
            forward_mock.assert_not_called()
            # (c) 503 status.
            assert resp.status_code == 503, (
                f"expected 503 when durable write fails, got {resp.status_code}: {resp.text}"
            )
            # (d) audit-specific message — differentiates this failure
            # from plain credentials-missing / vendor-503 responses.
            assert "durable audit" in resp.text.lower(), (
                f"503 body missing audit-specific message: {resp.text!r}"
            )
    finally:
        app.dependency_overrides.clear()
        settings.guard_use_durable_audit = _prev_flag
        settings.guard_durable_audit_fail_closed = _prev_fail
        settings.guard_durable_audit_rollout_pct = _prev_pct


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

    with patch("app.modules.guard.gateway_lifecycle.finalize", lambda *a, **kw: finalize_called.append(kw) or True), \
         patch("app.modules.guard.gateway_lifecycle.renew_lease", _raise_renew), \
         patch("app.guard.audit.renew_lease", _raise_renew):
        gen = _stream_chunks(client, resp, bg, audit_args, upstream_url=None)
        async for _ in gen:
            pass

    assert len(finalize_called) == 1
    assert finalize_called[0].get("execution_status") == "success"




# ─── P1 regression guard: heartbeat leak on forward exception ──────────


def test_forward_exception_stops_heartbeat_and_finalizes_error():
    """P1 review finding — forward + response-gate used to sit OUTSIDE
    any try/finally, so any exception between transport.forward() and
    close_durable_row() left the whole-request heartbeat running
    forever. renew_lease would keep bumping the row past the reconciler
    cutoff, permanently blocking cleanup.

    The fix wraps forward + gate in try/except/finally and, on error:
      (a) always runs close_durable_row (cancels renewal, idempotent),
      (b) best-effort-finalizes the row with execution_status='error'
          so it lands terminated immediately (reconciler doesn't have
          to sweep the abandoned lease later).

    Locks both invariants at the request-level, not the handler-body
    mental model.
    """
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock, patch, AsyncMock
    from app.main import app
    from app.core.database import get_db
    from app.core.config import settings

    _prev_flag = settings.guard_use_durable_audit
    _prev_pct  = settings.guard_durable_audit_rollout_pct
    settings.guard_use_durable_audit = True
    settings.guard_durable_audit_rollout_pct = 100  # #1995 canary — full rollout in tests

    db_mock = MagicMock()
    workspace_id = "00000000-0000-0000-0000-000000000abc"

    finalize_calls: list[dict] = []
    close_calls: list = []

    def _insert_ok(*a, **kw):
        return "row-abc-123"

    async def _capture_finalize(**kwargs):
        finalize_calls.append(kwargs)

    async def _capture_close(durable):
        close_calls.append(durable)

    forward_mock = AsyncMock(side_effect=RuntimeError("upstream socket died mid-forward"))

    class _FakeTransport:
        forward = forward_mock

    class _FakeRegistry:
        def for_provider(self, *a, **kw):
            return _FakeTransport()

    from app.guard.policy_types import PolicyAction, PolicyDecision
    _allow = PolicyDecision(action=PolicyAction.ALLOW, source="test")

    app.dependency_overrides[get_db] = lambda: db_mock

    try:
        with patch(
            "app.modules.guard.gateway_lifecycle.insert_accepted", _insert_ok,
        ), patch(
            "app.modules.guard.gateway_lifecycle.finalize_durable_row",
            _capture_finalize,
        ), patch(
            "app.modules.guard.gateway_lifecycle.close_durable_row",
            _capture_close,
        ), patch(
            "app.modules.guard.routers.proxy.get_provider_transport_registry",
            return_value=_FakeRegistry(),
        ), patch(
            "app.modules.guard.routers.proxy.resolve_agent_token",
            return_value=(workspace_id, "clerk_user_test"),
        ), patch(
            "app.modules.guard.routers.proxy.set_workspace_rls",
            lambda *a, **kw: None,
        ), patch(
            "app.modules.guard.routers.proxy.SessionLocal",
            lambda: db_mock,
        ), patch(
            "app.guard.policy.evaluate_composed", lambda ctx: _allow,
        ), patch(
            "app.modules.guard.routers.proxy._upstream_url",
            lambda db, ws, prov, env: "http://mock-upstream",
        ), patch(
            "app.modules.guard.routers.proxy._upstream_api_key",
            lambda db, ws, env: None,
        ), patch(
            "app.modules.guard.routers.proxy._vault_key",
            lambda db, ws, prov, env: "sk-fake",
        ), patch(
            "app.modules.guard.routers.proxy._flatten_prompt",
            lambda body: "hello",
        ), patch(
            "app.modules.guard.routers.proxy._estimate_input_tokens",
            lambda body: 10,
        ):
            client = TestClient(app, raise_server_exceptions=False)
            # Send a client X-Request-Id so we can also verify the
            # P2 fix (enriched routing_meta reaches the finalize call).
            client.post(
                "/proxy/anthropic/v1/messages",
                headers={
                    "x-api-key": "cond_agt_test",
                    "x-request-id": "client-correlation-abc",
                },
                json={"model": "claude-sonnet", "messages": [{"role": "user", "content": "hi"}]},
            )
    finally:
        app.dependency_overrides.clear()
        settings.guard_use_durable_audit = _prev_flag
        settings.guard_durable_audit_rollout_pct = _prev_pct

    # P1 (a) — close_durable_row MUST run even though forward raised.
    # Prior code path leaked the whole-request renewal task forever.
    assert close_calls, (
        "close_durable_row was NOT called when transport.forward raised — "
        "the whole-request heartbeat leaks and the row's lease will keep "
        "getting bumped past the reconciler cutoff."
    )

    # P1 (b) — best-effort finalize with 'error' status.
    assert len(finalize_calls) == 1, (
        f"expected one error-finalize call on the exception path, got "
        f"{len(finalize_calls)}: {finalize_calls!r}"
    )
    fc = finalize_calls[0]
    assert fc["execution_status"] == "error", (
        f"expected execution_status='error', got {fc.get('execution_status')!r}"
    )
    assert fc["row_id"] == "row-abc-123"
    assert "upstream socket died" in (fc.get("result_summary") or "")

    # P2 — enriched routing_meta MUST reach finalize (client_request_id
    # was pre-merged at the caller so the finalize UPDATE doesn't clobber
    # it back out via CAST(:routing AS jsonb)).
    assert fc.get("routing_meta", {}).get("client_request_id") == "client-correlation-abc", (
        "P2 fix regression — finalize routing_meta lost the client "
        "correlation. Enrichment must happen at the caller, not inside "
        "open_durable_row where the caller-side copy stays stale."
    )
