"""Test-wide fixtures. Kept minimal — most existing tests don't rely on
any conftest, so anything added here should be autouse-safe and cheap.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_gateway_revision_cache():
    """PR 6a — the gateway revision cache is a process-global singleton.
    Without clearing between tests, a revision_id used by test A leaks
    into test B and short-circuits the DB-mock path. Clear before every
    test to guarantee isolation.

    Fast — the cache is a small dict; clear() is O(size)."""
    try:
        from app.modules.guard.gateway_revision_cache import clear as _clear
        _clear()
    except Exception:
        pass
    yield
