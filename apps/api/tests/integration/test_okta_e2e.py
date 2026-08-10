"""
End-to-end Okta JWT auth test — hits a real Okta tenant + real Conduct API.

**Skipped by default**. Opt-in via env vars — CI runs the unit suite,
this file only runs when an operator explicitly points it at a live
dev tenant.

Required env vars:
  CONDUCT_OKTA_E2E              — set to "1" to enable
  OKTA_DOMAIN                   — e.g. integrator-2944519.okta.com
  OKTA_CLIENT_ID                — service app client_id
  OKTA_CLIENT_SECRET            — service app client_secret
  OKTA_AUDIENCE                 — expected `aud` on issued JWTs (e.g. api://default)
  CONDUCT_API_URL               — e.g. https://api.conductai.ai
  CONDUCT_WORKSPACE_ID          — workspace with okta_auth_enabled=true
  CONDUCT_ADMIN_TOKEN           — cond_agt_/cond_api_ with admin scope
                                  (needed to deactivate/reactivate the identity)
  OKTA_TEST_IDENTITY_ID         — AgentIdentity.id already synced from OKTA_CLIENT_ID

Optional:
  OKTA_AUTH_SERVER_ID           — Okta authorization server ID (default: "default")

Flow (all real network):
  1. Fetch a client_credentials JWT from Okta's /oauth2/{server}/v1/token
  2. Present it to Conduct's /auth/whoami — assert 200 + identity resolves
  3. PATCH the identity to lifecycle_state=deactivated
  4. Present the same JWT again — assert 401 with "deactivated"
  5. PATCH back to lifecycle_state=active
  6. Present again — assert 200 again

Never runs in CI. Never touches production data unless the operator points
CONDUCT_WORKSPACE_ID at production (their choice).
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("CONDUCT_OKTA_E2E") != "1",
    reason="Okta E2E disabled — set CONDUCT_OKTA_E2E=1 and required env vars to run",
)


def _env(key: str) -> str:
    v = os.environ.get(key)
    if not v:
        pytest.skip(f"Missing required env var: {key}")
    return v


@pytest.fixture(scope="module")
def okta_jwt() -> str:
    domain = _env("OKTA_DOMAIN")
    client_id = _env("OKTA_CLIENT_ID")
    client_secret = _env("OKTA_CLIENT_SECRET")
    server = os.environ.get("OKTA_AUTH_SERVER_ID", "default")

    body = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "agent.act",  # customize in Okta admin
    }).encode()
    req = urllib.request.Request(
        f"https://{domain}/oauth2/{server}/v1/token",
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    tok = payload.get("access_token")
    assert tok, f"No access_token in Okta response: {payload}"
    return tok


def _whoami(api: str, ws: str, jwt: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{api.rstrip('/')}/auth/whoami?workspace_id={ws}",
        headers={
            "Authorization": f"Bearer {jwt}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"detail": e.reason}


def _patch_identity(api: str, ws: str, admin_token: str, identity_id: str, lifecycle: str) -> int:
    body = json.dumps({"lifecycle_state": lifecycle}).encode()
    req = urllib.request.Request(
        f"{api.rstrip('/')}/workspaces/{ws}/agent-identities/{identity_id}?workspace_id={ws}",
        data=body,
        method="PATCH",
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.status


def test_okta_jwt_end_to_end_lifecycle(okta_jwt):
    api = _env("CONDUCT_API_URL")
    ws = _env("CONDUCT_WORKSPACE_ID")
    admin = _env("CONDUCT_ADMIN_TOKEN")
    identity_id = _env("OKTA_TEST_IDENTITY_ID")

    # 1) valid JWT resolves
    status, body = _whoami(api, ws, okta_jwt)
    assert status == 200, f"Expected 200, got {status}: {body}"
    assert body.get("token_kind") == "okta_jwt"
    assert body.get("identity") is not None
    assert body["identity"].get("lifecycle_state") == "active"

    # 2) deactivate → same JWT rejected
    assert _patch_identity(api, ws, admin, identity_id, "deactivated") in (200, 204)
    status, body = _whoami(api, ws, okta_jwt)
    assert status == 401
    assert "deactivated" in (body.get("detail") or "").lower()

    # 3) reactivate → JWT accepted again
    assert _patch_identity(api, ws, admin, identity_id, "active") in (200, 204)
    status, body = _whoami(api, ws, okta_jwt)
    assert status == 200, f"Expected 200 after reactivate, got {status}: {body}"
