"""PR 2 Commit 3 — regression guard for the DB-operation offload contract.

Locks in the pattern where the four hot-path DB operations in
``handle_gateway_request`` run via ``starlette.concurrency.run_in_threadpool``
so the FastAPI event loop is never blocked by sync SQLAlchemy calls.

If a future edit removes the ``run_in_threadpool`` wrap around any of
these, the throughput ceiling regresses to the pre-PR 2 behavior
(sync-in-async cliff at ~25 concurrent per worker). This file fails
loudly when that happens.
"""
from __future__ import annotations

from pathlib import Path

_HANDLER = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_handler.py"
).read_text(encoding="utf-8")

_HELPERS = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_helpers.py"
).read_text(encoding="utf-8")


def _preceded_by_run_in_threadpool(source: str, marker: str, *, window: int = 400) -> bool:
    """True iff ANY occurrence of ``marker`` in ``source`` has
    ``run_in_threadpool`` within the ``window`` chars immediately
    preceding it. Iterates all matches so imports (which precede the
    call sites) don't false-negative the check."""
    idx = 0
    while True:
        idx = source.find(marker, idx)
        if idx == -1:
            return False
        if "run_in_threadpool" in source[max(0, idx - window):idx]:
            return True
        idx += 1


def test_run_in_threadpool_is_imported():
    """gateway_handler.py must import run_in_threadpool at module scope."""
    assert "from starlette.concurrency import run_in_threadpool" in _HANDLER, (
        "gateway_handler.py is missing the run_in_threadpool import — the "
        "DB-offload contract is broken."
    )


def test_auth_resolution_runs_in_threadpool():
    """``_resolve_gateway_auth`` must be invoked via run_in_threadpool.
    A raw ``_resolve_gateway_auth(...)`` sync call reintroduces the
    event-loop-blocking behavior for the biggest DB op on the path."""
    assert _preceded_by_run_in_threadpool(_HANDLER, "_resolve_gateway_auth,"), (
        "``_resolve_gateway_auth`` must be called via run_in_threadpool. "
        "Sync invocation blocks the event loop during 3-7 DB round-trips "
        "of auth work per request."
    )


def test_upstream_credential_resolution_runs_in_threadpool():
    """``_resolve_upstream_credentials`` combines _upstream_url +
    _upstream_api_key + _vault_key into a single bounded session. Must
    be called via run_in_threadpool so the three sequential DB round-
    trips do not stall the event loop."""
    assert _preceded_by_run_in_threadpool(_HANDLER, "_resolve_upstream_credentials,"), (
        "``_resolve_upstream_credentials`` must be called via "
        "run_in_threadpool. Three sequential DB round-trips inline "
        "stall the event loop per request."
    )


def test_tier_resolution_runs_in_threadpool():
    """``_apply_tier_resolution`` touches DB via ``model_router``. Must
    run in threadpool."""
    assert _preceded_by_run_in_threadpool(_HANDLER, "_apply_tier_resolution_owned,"), (
        "``_apply_tier_resolution`` must be called via run_in_threadpool "
        "(it does a model_router DB lookup)."
    )


def test_response_gate_runs_in_threadpool():
    """``_apply_response_gate`` runs the policy evaluator, which reads
    rules from DB. Must run in threadpool."""
    assert _preceded_by_run_in_threadpool(_HANDLER, "_apply_response_gate,"), (
        "``_apply_response_gate`` must be called via run_in_threadpool "
        "(policy eval does DB reads)."
    )


def test_resolve_gateway_auth_owns_its_session():
    """The session-per-thread helper must open ``SessionLocal()`` at
    entry and close it in a ``finally`` regardless of exit path."""
    assert "def _resolve_gateway_auth(" in _HELPERS, (
        "_resolve_gateway_auth removed from gateway_helpers — offload "
        "contract broken."
    )
    # The wrapper body must open + close a session.
    start = _HELPERS.index("def _resolve_gateway_auth(")
    end = _HELPERS.index("def _resolve_gateway_auth_inner(", start)
    body = _HELPERS[start:end]
    assert "SessionLocal" in body, (
        "_resolve_gateway_auth wrapper must open its own SessionLocal."
    )
    assert "finally:" in body and "db.close()" in body, (
        "_resolve_gateway_auth must close its session in a finally, "
        "regardless of exit path. Otherwise, session leaks accumulate "
        "on auth errors."
    )


def test_resolve_upstream_credentials_owns_its_session():
    """The combined credential helper opens one session for all three
    lookups and closes it in finally."""
    assert "def _resolve_upstream_credentials(" in _HELPERS
    start = _HELPERS.index("def _resolve_upstream_credentials(")
    # Grab enough of the function body to see the close.
    body = _HELPERS[start:start + 1500]
    assert "SessionLocal" in body
    assert "set_workspace_rls" in body, (
        "_resolve_upstream_credentials must set RLS before doing the "
        "credential lookups on its fresh session."
    )
    assert "finally:" in body and "db.close()" in body, (
        "_resolve_upstream_credentials must close its session in a "
        "finally so it does not leak on exception."
    )
