"""Proves /admin/cache-stats surfaces every counter surface and
respects the same auth model as /metrics.

NOTE — do NOT ``importlib.reload(app.main)`` or reload settings here.
Reloading modules for one test corrupts every downstream test's
global state (this was flagged on the pool-overflow test as the
same landmine class). Instead patch ``settings.environment`` and
``settings.metrics_token`` in place via monkeypatch.setattr — the
endpoint reads them live on each request.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_open_in_local_returns_all_surfaces(monkeypatch, client):
    monkeypatch.setattr(settings, "environment", "local", raising=False)
    resp = client.get("/admin/cache-stats")
    assert resp.status_code == 200
    body = resp.json()
    for k in (
        "auth_cache",
        "effective_policy_cache",
        "invalidation_bus",
        "budget_ledger",
        "admission",
    ):
        assert k in body, f"missing key: {k}"
    # Lazy singletons always resolve.
    assert body["invalidation_bus"] is not None
    assert body["budget_ledger"] is not None
    assert body["admission"] is not None


def test_prod_without_token_rejects(monkeypatch, client):
    monkeypatch.setattr(settings, "environment", "production", raising=False)
    monkeypatch.setattr(settings, "metrics_token", "", raising=False)
    resp = client.get("/admin/cache-stats")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "metrics_token_required"}


def test_prod_with_correct_token_accepts(monkeypatch, client):
    monkeypatch.setattr(settings, "environment", "production", raising=False)
    monkeypatch.setattr(settings, "metrics_token", "test-secret", raising=False)
    resp = client.get(
        "/admin/cache-stats",
        headers={"X-Metrics-Token": "test-secret"},
    )
    assert resp.status_code == 200


def test_prod_with_wrong_token_rejects(monkeypatch, client):
    monkeypatch.setattr(settings, "environment", "production", raising=False)
    monkeypatch.setattr(settings, "metrics_token", "correct", raising=False)
    resp = client.get(
        "/admin/cache-stats",
        headers={"X-Metrics-Token": "wrong"},
    )
    assert resp.status_code == 401
