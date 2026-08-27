"""Endpoint 5xx probe — #1260 lazy variant.

Poke every write endpoint (POST/PUT/PATCH/DELETE) with:
  1. empty body           `{}`
  2. garbage extra fields `{"__garbage__": "xxx", "z": 42}`

Assert: response is 4xx, never 5xx. A 5xx from a malformed request
means the endpoint crashed instead of returning 400/422 — a bug that
schemathesis would catch too, but this file needs zero new deps.

Runs under the same DB / dependency_overrides pattern as
test_endpoint_matrix.py so authorized calls actually reach the handler
body (not stopped at auth).

Marker `probe` so per-PR CI runs it. Full schemathesis / hypothesis
coverage is deferred — see #1260 discussion.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import SessionLocal
from app.main import app

# ── Setup mirrors test_endpoint_matrix.py ─────────────────────────────────────
TEST_WS_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
UUID_ZERO = "00000000-0000-0000-0000-000000000000"
ADMIN_USER = "user_500_probe_admin"


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


DB_AVAILABLE = _db_available()
requires_db = pytest.mark.skipif(not DB_AVAILABLE, reason="Postgres not reachable")


def _sub(path: str) -> str:
    return re.sub(r"\{[^}]+\}", UUID_ZERO, path)


def _write_routes() -> list[dict]:
    out: list[dict] = []
    for r in app.routes:
        methods = getattr(r, "methods", None) or set()
        for m in {"POST", "PUT", "PATCH", "DELETE"} & methods:
            out.append({"method": m, "path": r.path, "url": _sub(r.path), "name": getattr(r, "name", "?")})
    return out


WRITE_ROUTES = _write_routes()


# Endpoints known to 500 on garbage input today — file follow-up bugs and
# remove from allowlist. Empty list is the eventual target.
KNOWN_500_ALLOWLIST: set[tuple[str, str]] = set()


@pytest.fixture(scope="module")
def probe_client():
    """TestClient with an admin identity so writes actually reach handlers."""
    with SessionLocal() as db:
        db.execute(
            text("""
                INSERT INTO workspaces (id, name, owner_id)
                VALUES (:ws, 'test-probe', :uid)
                ON CONFLICT (id) DO NOTHING
            """),
            {"ws": str(TEST_WS_ID), "uid": ADMIN_USER},
        )
        db.commit()

    app.dependency_overrides[get_user_id] = lambda: ADMIN_USER
    app.dependency_overrides[get_workspace_id] = lambda: str(TEST_WS_ID)
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_user_id, None)
        app.dependency_overrides.pop(get_workspace_id, None)


BAD_BODIES = [
    ("empty", {}),
    ("garbage", {"__garbage__": "xxx", "z": 42, "nested": {"deep": [1, 2]}}),
]


@requires_db
@pytest.mark.probe
@pytest.mark.parametrize(
    "route",
    WRITE_ROUTES,
    ids=[f'{r["method"]} {r["path"]}' for r in WRITE_ROUTES] or ["no-routes"],
)
@pytest.mark.parametrize("label,body", BAD_BODIES, ids=[label for label, _ in BAD_BODIES])
def test_write_endpoints_do_not_500_on_bad_body(probe_client, route, label, body):
    key = (route["method"], route["path"])
    if key in KNOWN_500_ALLOWLIST:
        pytest.xfail(f"{route['method']} {route['path']} is on the KNOWN_500_ALLOWLIST — file a bug and remove from allowlist")

    resp = probe_client.request(route["method"], route["url"], json=body)

    assert resp.status_code < 500, (
        f"{route['method']} {route['path']} returned {resp.status_code} on {label} body — "
        f"expected 4xx. Body: {resp.text[:200]}"
    )
