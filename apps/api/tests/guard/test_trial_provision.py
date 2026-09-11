"""Trial provisioning + redemption tests (audit S01 / S12 hardened flow).

The old /provision returned a decrypted trial token to anyone who guessed
an existing customer's email. These tests lock in the replacement:

- /provision NEVER returns a token; always returns a generic accepted body
- /provision NEVER leaks whether the email exists in Clerk
- /redeem verifies a single-use, TTL-bounded challenge before minting anything
- Existing-email challenges resolve to a sign-in URL only
- Rate limits + Redis mint both fail CLOSED (no free issuance without abuse controls)
"""
from __future__ import annotations

import uuid as _uuid
from contextlib import ExitStack
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


def _patch_provision(
    stack: ExitStack,
    *,
    existing_clerk_user_id: str | None = None,
    mint_token: str | None = "verify-token-xyz",
    ip_throttle: bool = True,
    email_rate: bool = True,
    global_rate: bool = True,
    email_sent: bool = True,
) -> None:
    """Patch everything /provision touches so no test hits real Redis/Clerk/Resend."""
    stack.enter_context(patch("app.modules.guard.routers.trial._throttle_by_ip", return_value=ip_throttle))
    stack.enter_context(patch("app.modules.guard.routers.trial._check_email_rate", return_value=email_rate))
    stack.enter_context(patch("app.modules.guard.routers.trial._check_global_rate", return_value=global_rate))
    stack.enter_context(patch("app.core.clerk.find_user_by_email", return_value=existing_clerk_user_id))
    stack.enter_context(patch("app.modules.guard.routers.trial._mint_challenge", return_value=mint_token))
    stack.enter_context(patch("app.modules.guard.routers.trial.send_template_email", return_value=email_sent))


# ── /provision — validation ─────────────────────────────────────────────────

def test_provision_rejects_invalid_email():
    client = _client(MagicMock())
    try:
        resp = client.post("/guard/trial/provision", json={"email": "not-an-email", "company": "Acme"})
        assert resp.status_code == 422
        assert "invalid_email" in resp.text
    finally:
        _clear()


def test_provision_requires_company():
    client = _client(MagicMock())
    try:
        resp = client.post("/guard/trial/provision", json={"email": "user@example.com", "company": "  "})
        assert resp.status_code == 422
        assert "company_required" in resp.text
    finally:
        _clear()


# ── /provision — S01 core invariant: never leak user existence ─────────────

def test_provision_returns_identical_ack_for_new_and_existing_emails():
    """New and existing emails must produce byte-identical response bodies.
    Any difference would let an anonymous caller enumerate registered emails.
    """
    client = _client(MagicMock())
    bodies: list[dict] = []
    for existing in (None, "user_abc"):
        try:
            with ExitStack() as stack:
                _patch_provision(stack, existing_clerk_user_id=existing)
                resp = client.post(
                    "/guard/trial/provision",
                    json={"email": "user@example.com", "company": "Acme"},
                )
            assert resp.status_code == 200
            bodies.append(resp.json())
        finally:
            _clear()
    assert bodies[0] == bodies[1]
    assert "agent_token" not in bodies[0]     # audit S01 — never in provision response
    assert "workspace_id" not in bodies[0]
    assert "sign_in_url" not in bodies[0]


def test_provision_returns_accepted_even_when_email_send_fails():
    """Email service down must still return accepted — surfacing failure
    would leak that the email was actually queued (i.e. valid)."""
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_provision(stack, email_sent=False)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "user@example.com", "company": "Acme"},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"
    finally:
        _clear()


# ── /provision — S12 fail-closed rate limits ────────────────────────────────

def test_provision_rejects_when_ip_throttle_fails():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_provision(stack, ip_throttle=False)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "user@example.com", "company": "Acme"},
            )
        assert resp.status_code == 429
    finally:
        _clear()


def test_provision_rejects_when_email_rate_fails():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_provision(stack, email_rate=False)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "user@example.com", "company": "Acme"},
            )
        assert resp.status_code == 429
    finally:
        _clear()


def test_provision_rejects_when_global_rate_fails():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_provision(stack, global_rate=False)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "user@example.com", "company": "Acme"},
            )
        assert resp.status_code == 429
    finally:
        _clear()


def test_provision_fails_closed_when_mint_returns_none():
    """Redis outage during mint returns None — endpoint must 503, not
    silently swallow (audit S12)."""
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_provision(stack, mint_token=None)
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "user@example.com", "company": "Acme"},
            )
        assert resp.status_code == 503
        assert "verification_unavailable" in resp.text
    finally:
        _clear()


# ── /redeem — happy paths ───────────────────────────────────────────────────

def _mk_challenge(*, existing_user_id: str | None):
    from app.modules.guard.trial_challenges import Challenge
    return Challenge(
        email="user@example.com",
        company="Acme",
        existing_user_id=existing_user_id,
        created_at=1_700_000_000.0,
    )


def _patch_redeem(
    stack: ExitStack,
    *,
    challenge=None,
    ip_throttle: bool = True,
    new_clerk_user_id: str = "user_new_123",
    workspace_uuid=None,
    ident_row=None,
    sign_in_url: str | None = None,
    create_raises=None,
):
    """Patch everything /redeem touches."""
    stack.enter_context(patch("app.modules.guard.routers.trial._throttle_by_ip", return_value=ip_throttle))
    stack.enter_context(patch("app.modules.guard.routers.trial._redeem_challenge", return_value=challenge))
    if create_raises:
        stack.enter_context(patch("app.core.clerk.create_user", side_effect=create_raises))
    else:
        stack.enter_context(patch("app.core.clerk.create_user", return_value=new_clerk_user_id))
    stack.enter_context(patch(
        "app.modules.onboarding.provision_workspace_for_user",
        return_value=workspace_uuid or _uuid.uuid4(),
    ))
    stack.enter_context(patch(
        "app.modules.guard.routers.trial._load_trial_identity",
        return_value=ident_row or SimpleNamespace(
            id=_uuid.uuid4(), token_encrypted=b"blob", expires_at=None,
        ),
    ))
    stack.enter_context(patch(
        "app.modules.guard.routers.trial.decrypt",
        return_value={"token": "cond_agt_trial_deadbeef"},
    ))
    stack.enter_context(patch("app.core.clerk.mint_sign_in_token", return_value=sign_in_url))


def test_redeem_new_email_returns_workspace_and_token():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(stack, challenge=_mk_challenge(existing_user_id=None))
            resp = client.post("/guard/trial/redeem", json={"ct": "verify-token-xyz"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "new"
        assert body["agent_token"] == "cond_agt_trial_deadbeef"
        assert body["workspace_id"]
        assert body["gateway_url"].endswith("/anthropic")
    finally:
        _clear()


def test_redeem_existing_email_returns_recovery_url_only():
    """S01 core: existing-email challenges never issue a token."""
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(stack, challenge=_mk_challenge(existing_user_id="user_existing_abc"))
            # If clerk.create_user gets called we'd blow the fixture — proves
            # we short-circuited before touching Clerk.
            stack.enter_context(patch(
                "app.core.clerk.create_user",
                side_effect=AssertionError("must not be called for existing user"),
            ))
            resp = client.post("/guard/trial/redeem", json={"ct": "verify-token-xyz"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "existing"
        assert body["agent_token"] is None
        assert body["workspace_id"] is None
        assert body["recovery_url"]
    finally:
        _clear()


# ── /redeem — invalid / expired / double-redeem all look the same ──────────

def test_redeem_unknown_or_expired_token_returns_410():
    """`_redeem_challenge` returns None for unknown, expired, and already
    redeemed tokens — endpoint returns the same 410 for all three so an
    attacker can't distinguish."""
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(stack, challenge=None)
            resp = client.post("/guard/trial/redeem", json={"ct": "anything"})
        assert resp.status_code == 410
        assert "challenge_invalid_or_expired" in resp.text
    finally:
        _clear()


def test_redeem_requires_ct():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(stack, challenge=None)
            resp = client.post("/guard/trial/redeem", json={"ct": "  "})
        assert resp.status_code == 422
        assert "challenge_required" in resp.text
    finally:
        _clear()


def test_redeem_rate_limited_by_ip():
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(stack, challenge=_mk_challenge(existing_user_id=None), ip_throttle=False)
            resp = client.post("/guard/trial/redeem", json={"ct": "verify-token-xyz"})
        assert resp.status_code == 429
    finally:
        _clear()


def test_redeem_clerk_422_race_degrades_to_existing():
    """Race: user signs up in browser between /provision and /redeem.
    Clerk's create_user returns 422 (email taken). Instead of leaking
    that fact, degrade to the same 'existing' response."""
    from app.core.clerk import ClerkError
    client = _client(MagicMock())
    try:
        with ExitStack() as stack:
            _patch_redeem(
                stack,
                challenge=_mk_challenge(existing_user_id=None),
                create_raises=ClerkError(status=422, message="email exists"),
            )
            resp = client.post("/guard/trial/redeem", json={"ct": "verify-token-xyz"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "existing"
        assert body["agent_token"] is None
    finally:
        _clear()
