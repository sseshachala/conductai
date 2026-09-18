"""R3 (reviewer P1) — async offload of DB+Redis work + bounded timeouts.

The gateway handler is an async coroutine. Pre-fix, the reservation
path opened a SessionLocal on the event loop, ran a sync
``_reserve_budgets_for_request`` (SQL queries + Redis Lua eval) inline,
held the session across the upstream await, then ran a sync
settle+commit at the end — all on the loop. Under concurrency this is
the same load-stall class the auth cache fix (PR 6-series) closed.
Reviewer R3 called it out as a hard blocker.

Fix pattern (post-R3):

- Reserve runs inside ``_reserve_sync_owned()`` — a local function
  that opens the session, calls the helper, closes the session — and
  the handler awaits ``run_in_threadpool(_reserve_sync_owned)``. No
  session is held across the upstream await.
- Settle uses the same pattern with ``_settle_sync_owned()``.
- The Redis client pool now has explicit ``socket_timeout`` and
  ``socket_connect_timeout`` so a stalled Redis fails fast (2s/1.5s
  defaults) instead of parking a threadpool worker forever.

Structural tests here — the runtime behavior guard is the chaos
suite in the epic. If a regression collapses back to sync-on-loop
these tests fail loudly at CI time.
"""
from __future__ import annotations

import inspect


def test_reserve_runs_in_threadpool():
    """Handler must offload the reservation call so the event loop
    stays responsive during a slow DB or Redis."""
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    assert "await run_in_threadpool(_reserve_sync_owned)" in src, (
        "R3 regressed: reserve is back on the event loop. Wrap the "
        "reserve call in a run_in_threadpool helper that owns its own "
        "SessionLocal lifecycle."
    )


def test_settle_runs_in_threadpool():
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    assert "await run_in_threadpool(_settle_sync_owned)" in src, (
        "R3 regressed: settle is back on the event loop. Wrap the "
        "settle call in a run_in_threadpool helper."
    )


def test_no_shared_session_held_across_await():
    """The pre-R3 code held ``_budget_wire_db = SessionLocal()`` from
    before the reservation through to after the upstream await. Post-
    R3 no such shared session exists in the reserve-settle wire."""
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    assert "_budget_wire_db = SessionLocal()" not in src, (
        "R3 regressed: SessionLocal held across upstream await. Move "
        "the SessionLocal call inside the run_in_threadpool helper."
    )


def test_reserve_sync_helper_owns_session_lifecycle():
    """The threadpool helper must open + close its own SessionLocal —
    otherwise a caught reserve exception leaks the session."""
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    idx = src.index("def _reserve_sync_owned")
    body = src[idx : idx + 1800]
    assert "_db = SessionLocal()" in body, "reserve helper must open its own session"
    assert "_db.close()" in body, "reserve helper must close its own session (finally)"
    assert "finally:" in body, "reserve helper must guarantee close via finally"


def test_settle_sync_helper_owns_session_lifecycle():
    import app.modules.guard.gateway_handler as gh

    src = inspect.getsource(gh)
    idx = src.index("def _settle_sync_owned")
    body = src[idx : idx + 2000]
    assert "_db = SessionLocal()" in body, "settle helper must open its own session"
    assert "_db.commit()" in body, "settle helper must commit its own session"
    assert "_db.close()" in body, "settle helper must close its own session"
    assert "finally:" in body


def test_redis_pool_has_bounded_socket_timeouts():
    """A Redis blip must fail fast, not park a threadpool worker."""
    from app.core.budget_ledger import (
        _REDIS_CONNECT_TIMEOUT_SEC,
        _REDIS_SOCKET_TIMEOUT_SEC,
    )

    assert 0 < _REDIS_SOCKET_TIMEOUT_SEC <= 10, (
        "socket_timeout must be a small positive value (fail-fast). "
        f"got {_REDIS_SOCKET_TIMEOUT_SEC}s"
    )
    assert 0 < _REDIS_CONNECT_TIMEOUT_SEC <= _REDIS_SOCKET_TIMEOUT_SEC, (
        "socket_connect_timeout must be <= socket_timeout. "
        f"got connect={_REDIS_CONNECT_TIMEOUT_SEC}s socket={_REDIS_SOCKET_TIMEOUT_SEC}s"
    )


def test_redis_pool_wires_the_timeouts_into_from_url():
    """Grep-guard: the ConnectionPool.from_url() call must actually pass
    the two timeout kwargs. Setting the constants without wiring them
    would silently regress."""
    import inspect

    from app.core import budget_ledger

    src = inspect.getsource(budget_ledger._r)
    assert "socket_timeout=_REDIS_SOCKET_TIMEOUT_SEC" in src, (
        "socket_timeout not wired into ConnectionPool.from_url()"
    )
    assert "socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SEC" in src, (
        "socket_connect_timeout not wired into ConnectionPool.from_url()"
    )
