"""#1751 PR 5 — GET /guard/policies/packs/{slug}/coverage-matrix endpoint.

Wires PackCoverageMatrixOut over the pack_coverage_matrix helper. Auth
via require_permission("guard.policies.view") — conftest.py stubs the
permission check to a noop, so we can hit the endpoint directly.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client():
    from app.main import app
    from app.core.database import get_db
    from app.core.auth import get_workspace_id, get_user_id

    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_workspace_id] = lambda: "ws-abc"
    app.dependency_overrides[get_user_id] = lambda: "user_test"
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    from app.main import app
    app.dependency_overrides.clear()


def test_pack_coverage_endpoint_returns_helper_output():
    fake = {
        "pack": "conduct-hipaa",
        "version": "1.4.2",
        "total_rules": 3,
        "by_surface": {
            "mcp":     {"hard": 2, "not_supported": 1},
            "proxy":   {"hard": 1, "not_supported": 2},
            "runtime": {"hard": 2, "not_supported": 1},
            "hook":    {"hard": 2, "not_supported": 1},
        },
        "by_gate": {"action": 2, "prompt": 1, "response": 0},
    }
    try:
        with patch(
            "app.modules.guard.coverage.pack_coverage_matrix",
            return_value=fake,
        ):
            client = _client()
            r = client.get("/guard/policies/packs/conduct-hipaa/coverage-matrix")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["pack"] == "conduct-hipaa"
        assert body["version"] == "1.4.2"
        assert body["total_rules"] == 3
        assert body["by_surface"]["proxy"] == {"hard": 1, "not_supported": 2}
        assert body["by_gate"]["response"] == 0
    finally:
        _clear()


def test_missing_pack_returns_zero_envelope():
    fake = {
        "pack": "conduct-fake",
        "version": None,
        "total_rules": 0,
        "by_surface": {
            "mcp":     {"hard": 0, "not_supported": 0},
            "proxy":   {"hard": 0, "not_supported": 0},
            "runtime": {"hard": 0, "not_supported": 0},
            "hook":    {"hard": 0, "not_supported": 0},
        },
        "by_gate": {"action": 0, "prompt": 0, "response": 0},
    }
    try:
        with patch(
            "app.modules.guard.coverage.pack_coverage_matrix",
            return_value=fake,
        ):
            client = _client()
            r = client.get("/guard/policies/packs/conduct-fake/coverage-matrix")
        assert r.status_code == 200
        body = r.json()
        assert body["version"] is None
        assert body["total_rules"] == 0
    finally:
        _clear()
