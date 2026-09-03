"""Wire-in assertion for #1587 E1 — vault-key RPM/TPM fence in the proxy.

Migration 0096 documented that `check_rate_limit` should be called from
`_proxy` step 4d, but the wiring never landed until #1587 E1. This test
guards against future refactors silently removing the fence.

Complements the module-level smoke tests in test_rate_limit_smoke.py —
those prove check_rate_limit works; this proves the proxy calls it.
"""
from __future__ import annotations

import inspect

import pytest


def test_proxy_module_imports_check_rate_limit():
    """The proxy module source must contain the check_rate_limit import."""
    from app.modules.guard.routers import proxy
    source = inspect.getsource(proxy)
    assert "check_rate_limit" in source, (
        "Proxy hot path is missing check_rate_limit — #1587 E1 wire-in "
        "was reverted or refactored away. See migration 0096 for the "
        "expected call site."
    )


def test_proxy_returns_429_on_rate_limit():
    """The wire-in must convert `limited=True` into a 429 response,
    not a silent pass. Grep for the specific error code so a refactor
    that changes the response code (e.g., to 503) trips this test."""
    from app.modules.guard.routers import proxy
    source = inspect.getsource(proxy)
    # Find the block that references _rate.limited and confirm 429 lives
    # within a small window (30 lines) — tolerates reformatting.
    idx = source.find("_rate.limited")
    assert idx > 0, "no _rate.limited branch found — wire-in missing"
    window = source[idx:idx + 800]
    assert "429" in window, (
        "rate-limit 429 response missing from proxy — E1 wire-in "
        "changed the failure mode."
    )
