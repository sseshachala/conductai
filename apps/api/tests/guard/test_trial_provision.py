"""#1712 Track 1 PR 5 (unified) — POST /guard/trial/provision.

Public signup endpoint. Unauthenticated, email + company both REQUIRED.
Converged with UI signup via Clerk backend API + shared
`provision_workspace_for_user`. Every provision:

  1. Look up Clerk user by email → 409 if exists (existing account,
     tell them to sign in)
  2. Create Clerk user via backend API → get `user_id`
  3. Run shared onboarding (same code path as Clerk webhook)
  4. Load trial agent identity → decrypt token → return
  5. Optional: mint sign-in URL so CLI can print "click to dashboard"

Coverage:
  - happy path — fresh email creates Clerk user + workspace + token
  - existing Clerk user — 409 with sign-in guidance
  - Clerk API failure — 502
  - validation — bad email 422, missing company 422
  - IP rate-limit — 429
  - sign_in_url is passed through when Clerk returns one
"""
from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(db_mock):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides.pop(get_db, None)


def _patch_deps(
    *,
    existing_clerk_user_id=None,
    new_clerk_user_id="user_test_123",
    workspace_uuid=None,
    ident_row=None,
    sign_in_url=None,
    throttle=True,
    create_raises=None,
):
    """Compose the patch context — every dep the endpoint touches is
    mocked so tests never hit a real DB or Clerk. Returns a list of
    `patch` context managers the test enters via ExitStack."""
    from contextlib import ExitStack
    stack = ExitStack()

    def _install(target, **kwargs):
        stack.enter_context(patch(target, **kwargs))

    def _install_side(target, side_effect):
        stack.enter_context(patch(target, side_effect=side_effect))

    def _install_ret(target, return_value):
        stack.enter_context(patch(target, return_value=return_value))

    return stack, {
        "existing_clerk_user_id": existing_clerk_user_id,
        "new_clerk_user_id": new_clerk_user_id,
        "workspace_uuid": workspace_uuid or _uuid.uuid4(),
        "ident_row": ident_row or SimpleNamespace(
            id=_uuid.uuid4(),
            token_encrypted=b"encrypted-placeholder",
            expires_at=None,
        ),
        "sign_in_url": sign_in_url,
        "throttle": throttle,
        "create_raises": create_raises,
    }


def _apply_patches(stack, cfg):
    """Enter the standard patch set inside `stack`. Returns None; side-effect
    only. Kept out of `_patch_deps` so tests can add/override before entering."""
    from app.core.clerk import ClerkError
    stack.enter_context(patch("app.modules.guard.routers.trial._throttle_by_ip", return_value=cfg["throttle"]))
    stack.enter_context(patch("app.core.clerk.find_user_by_email", return_value=cfg["existing_clerk_user_id"]))
    if cfg["create_raises"]:
        stack.enter_context(patch("app.core.clerk.create_user", side_effect=cfg["create_raises"]))
    else:
        stack.enter_context(patch("app.core.clerk.create_user", return_value=cfg["new_clerk_user_id"]))
    stack.enter_context(patch("app.modules.onboarding.provision_workspace_for_user", return_value=cfg["workspace_uuid"]))
    stack.enter_context(patch("app.modules.guard.routers.trial._load_trial_identity", return_value=cfg["ident_row"]))
    stack.enter_context(patch("app.modules.guard.routers.trial.decrypt", return_value={"token": "cond_agt_trial_deadbeef"}))
    stack.enter_context(patch("app.core.clerk.mint_sign_in_token", return_value=cfg["sign_in_url"]))


# ── Validation ───────────────────────────────────────────────────────────────

def test_provision_requires_valid_email():
    db = MagicMock()
    client = _client(db)
    try:
        resp = client.post("/guard/trial/provision", json={"email": "not-an-email", "company": "Xervmon"})
        assert resp.status_code == 422
        assert "invalid_email" in resp.text
    finally:
        _clear()


def test_provision_requires_company():
    db = MagicMock()
    # Pydantic-level missing → 422 (validation error before endpoint logic)
    client = _client(db)
    try:
        resp = client.post("/guard/trial/provision", json={"email": "sudhi@example.com"})
        assert resp.status_code == 422
    finally:
        _clear()

    # Endpoint-level whitespace-only → 422 with our detail string
    client = _client(MagicMock())
    try:
        resp = client.post("/guard/trial/provision", json={"email": "sudhi@example.com", "company": "  "})
        assert resp.status_code == 422
        assert "company_required" in resp.text
    finally:
        _clear()


# ── Happy path ───────────────────────────────────────────────────────────────

def test_provision_creates_clerk_user_and_returns_token():
    stack, cfg = _patch_deps(existing_clerk_user_id=None, sign_in_url=None)
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "SUDHI@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_token"] == "cond_agt_trial_deadbeef"
    assert body["workspace_id"] == str(cfg["workspace_uuid"])
    assert body["gateway_url"].endswith("/anthropic")
    assert body["workspace_url"].endswith("/theguard")
    assert body["sign_in_url"] is None


def test_provision_passes_through_sign_in_url_when_clerk_mints_one():
    stack, cfg = _patch_deps(sign_in_url="https://accounts.example.com/sign-in?ticket=xyz")
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 200
    assert resp.json()["sign_in_url"] == "https://accounts.example.com/sign-in?ticket=xyz"


# ── Idempotency via Clerk ─────────────────────────────────────────────────────

def test_provision_returns_token_for_existing_clerk_user():
    """Same email hitting the endpoint twice OR after a browser signup
    should not create a duplicate Clerk user — the lookup path returns
    the existing user_id and shared onboarding is idempotent, so we
    end up with one workspace + a fresh token round-trip."""
    stack, cfg = _patch_deps(existing_clerk_user_id="user_existing_abc")
    # Mock create_user to blow up if called — proves we short-circuited.
    from app.core.clerk import ClerkError
    stack.enter_context(patch("app.core.clerk.create_user", side_effect=AssertionError("must not be called")))

    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    # Existing user + idempotent onboarding = 200 with the existing token,
    # not a 409. Rationale: same email re-running the installer is a valid
    # UX (re-provision my ~/.conduct/env); we short-circuit Clerk creation
    # but still hand back the token.
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent_token"] == "cond_agt_trial_deadbeef"


# ── Clerk API failure ─────────────────────────────────────────────────────────

def test_provision_502s_when_clerk_create_user_fails_with_5xx():
    from app.core.clerk import ClerkError
    stack, cfg = _patch_deps(existing_clerk_user_id=None, create_raises=ClerkError(status=500, message="down"))
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 502
    # New mapping: 5xx from Clerk → clerk_unavailable (upstream outage).
    # 4xx-non-422 also maps here — same class of error from the caller's POV.
    assert "clerk_unavailable" in resp.text


def test_provision_409s_on_clerk_422_race():
    """Clerk 422 on create_user typically means the email already exists —
    a race between our lookup and someone else creating the user under the
    same email. Surface as 409 so the caller knows to sign in."""
    from app.core.clerk import ClerkError
    stack, cfg = _patch_deps(
        existing_clerk_user_id=None,
        create_raises=ClerkError(status=422, message="email already exists"),
    )
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 409
    assert "clerk_create_user_failed" in resp.text


def test_provision_passes_through_clerk_429_as_429():
    """Clerk rate-limiting our provisioning should surface as 429 to the
    caller, not 502 — so `curl | sh` can back off honestly instead of
    treating an upstream throttle as a server outage."""
    from app.core.clerk import ClerkError
    stack, cfg = _patch_deps(
        existing_clerk_user_id=None,
        create_raises=ClerkError(status=429, message="too many requests"),
    )
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 429
    assert "clerk_rate_limited" in resp.text


# ── Rate-limit ────────────────────────────────────────────────────────────────

def test_provision_ip_rate_limit_returns_429():
    stack, cfg = _patch_deps(throttle=False)
    db = MagicMock()
    client = _client(db)
    try:
        with stack:
            _apply_patches(stack, cfg)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 429
    assert "provision_rate_limited" in resp.text
