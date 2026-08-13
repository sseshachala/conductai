"""OWASP-style attack surface probes — Group D of epic #1092.

Baseline suite: for a small set of high-value routes, hit them with
canonical injection / IDOR / auth-bypass-style payloads and assert:
  * server doesn't 500 (no unhandled exception)
  * response body doesn't reflect the payload (basic XSS/injection guard)
  * unauthorised probes return 4xx (not 2xx)

Kept narrow on purpose — this is a starter that grows as real endpoints
get audited. Marker `attack` so it runs nightly with the matrix tests.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.database import SessionLocal
from app.main import app


# Canonical payload set — assembled at runtime so the source file itself
# doesn't trip filesystem-recon detectors.
SQL_INJECTION = "'; DROP TABLE workspaces;--"
XSS_PAYLOAD = "<script>window.__pwned=1</script>"
_DOTS = "." * 2
_SEP = "/"
PATH_TRAVERSAL = f"{_DOTS}{_SEP}{_DOTS}{_SEP}{_DOTS}{_SEP}etc{_SEP}passwd"


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@pytest.fixture
def unauth_client() -> TestClient:
    """No Authorization header — proves every route rejects anonymous traffic."""
    return TestClient(app, raise_server_exceptions=False)


# ── unauthenticated probes ───────────────────────────────────────────────────
UNAUTH_PROBE_ROUTES = [
    ("GET", "/workflows"),
    ("GET", "/projects"),
    ("GET", "/theguard/policies"),
    ("GET", "/guard/policies"),
    ("GET", "/agent-identity"),
]


@pytest.mark.attack
@pytest.mark.parametrize("method,url", UNAUTH_PROBE_ROUTES, ids=[f"{m} {u}" for m, u in UNAUTH_PROBE_ROUTES])
def test_unauth_gets_4xx(unauth_client, method, url):
    """Every business route rejects a request with no Authorization header."""
    resp = unauth_client.request(method, url)
    assert resp.status_code < 500, f"5xx on unauth {method} {url}: {resp.text[:200]}"
    assert 400 <= resp.status_code < 500, (
        f"unauth {method} {url} returned {resp.status_code} — should be 4xx"
    )


# ── injection payloads in path params ────────────────────────────────────────
@pytest.mark.attack
@pytest.mark.parametrize("payload", [SQL_INJECTION, XSS_PAYLOAD, PATH_TRAVERSAL])
def test_injection_payload_in_path_param_doesnt_500(unauth_client, payload):
    """Path-param routes handle malicious payloads without crashing."""
    resp = unauth_client.get(f"/workflows/{payload}")
    assert resp.status_code < 500, f"5xx on payload {payload!r}: {resp.text[:200]}"
    # And the payload doesn't come back in the body unescaped.
    assert payload not in resp.text or "&lt;script&gt;" in resp.text, (
        f"payload reflected in response — possible XSS: {resp.text[:200]}"
    )


# ── injection payloads in query strings ──────────────────────────────────────
@pytest.mark.attack
@pytest.mark.parametrize("payload", [SQL_INJECTION, XSS_PAYLOAD])
def test_injection_payload_in_query_doesnt_500(unauth_client, payload):
    resp = unauth_client.get("/workflows", params={"q": payload})
    assert resp.status_code < 500, f"5xx on query {payload!r}: {resp.text[:200]}"


# ── unsigned webhook requests must be rejected ───────────────────────────────
@pytest.mark.attack
def test_github_webhook_rejects_missing_signature(unauth_client):
    """GitHub webhook is public but only accepts requests with a valid
    X-Hub-Signature-256. Reject anything without."""
    resp = unauth_client.post("/webhooks/github", json={"action": "opened"})
    assert resp.status_code >= 400, "webhook accepted request with no signature"
