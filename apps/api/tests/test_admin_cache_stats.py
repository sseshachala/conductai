"""Proves /admin/cache-stats surfaces every counter surface and
respects the same auth model as /metrics.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    # Force local so token is optional — dedicated test below checks
    # prod fail-closed behavior with an explicit patch.
    monkeypatch.setenv("ENVIRONMENT", "local")
    yield


def _client():
    from app.main import app
    return TestClient(app)


def test_open_in_local_returns_all_surfaces():
    resp = _client().get("/admin/cache-stats")
    assert resp.status_code == 200
    body = resp.json()
    # All five surfaces present as keys — a missing key means the
    # endpoint regressed and lost a subsystem.
    for k in (
        "auth_cache",
        "effective_policy_cache",
        "invalidation_bus",
        "budget_ledger",
        "admission",
    ):
        assert k in body, f"missing key: {k}"
    # invalidation_bus + budget_ledger + admission always resolve
    # (lazy singleton). auth_cache/policy_cache may be None if the
    # startup init hasn't run in the test app.
    assert body["invalidation_bus"] is not None
    assert body["budget_ledger"] is not None
    assert body["admission"] is not None


def test_prod_without_token_rejects(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Force a fresh settings import so the environment change takes hold.
    import importlib
    from app.core import config as _cfg
    importlib.reload(_cfg)
    from app import main as _main
    importlib.reload(_main)
    client = TestClient(_main.app)
    resp = client.get("/admin/cache-stats")
    assert resp.status_code == 401


def test_prod_with_correct_token_accepts(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("METRICS_TOKEN", "test-secret-value")
    import importlib
    from app.core import config as _cfg
    importlib.reload(_cfg)
    from app import main as _main
    importlib.reload(_main)
    client = TestClient(_main.app)
    resp = client.get(
        "/admin/cache-stats",
        headers={"X-Metrics-Token": "test-secret-value"},
    )
    assert resp.status_code == 200


def test_prod_with_wrong_token_rejects(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("METRICS_TOKEN", "correct")
    import importlib
    from app.core import config as _cfg
    importlib.reload(_cfg)
    from app import main as _main
    importlib.reload(_main)
    client = TestClient(_main.app)
    resp = client.get(
        "/admin/cache-stats",
        headers={"X-Metrics-Token": "wrong"},
    )
    assert resp.status_code == 401
