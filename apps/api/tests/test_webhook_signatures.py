"""
Unit tests for the three webhook signature verification functions in
app/routers/webhooks.py. No network, no DB, no fixtures required.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from unittest.mock import patch

from app.routers.webhooks import (
    _verify_clerk_signature,
    _verify_github_signature,
    _verify_slack_signature,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slack_sig(body: bytes, timestamp: str, secret: str) -> str:
    base = f"v0:{timestamp}:{body.decode()}"
    return "v0=" + hmac.new(secret.encode(), base.encode(), hashlib.sha256).hexdigest()


def _github_sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _clerk_sig(svix_id: str, svix_timestamp: str, body: bytes, raw_secret: bytes) -> str:
    signed = f"{svix_id}.{svix_timestamp}.{body.decode()}"
    digest = hmac.new(raw_secret, signed.encode(), hashlib.sha256).digest()
    return "v1," + base64.b64encode(digest).decode()


# ---------------------------------------------------------------------------
# _verify_slack_signature
# ---------------------------------------------------------------------------

def test_slack_valid_signature():
    body = b'{"event": "test"}'
    ts = str(int(time.time()))
    secret = "test_slack_secret"
    sig = _slack_sig(body, ts, secret)
    assert _verify_slack_signature(body, ts, sig, secret) is True


def test_slack_empty_signing_secret():
    body = b'{"event": "test"}'
    ts = str(int(time.time()))
    sig = _slack_sig(body, ts, "any_secret")
    assert _verify_slack_signature(body, ts, sig, "") is False


def test_slack_timestamp_too_old():
    body = b'{"event": "test"}'
    ts = str(int(time.time()) - 301)
    secret = "test_slack_secret"
    sig = _slack_sig(body, ts, secret)
    assert _verify_slack_signature(body, ts, sig, secret) is False


def test_slack_timestamp_too_future():
    body = b'{"event": "test"}'
    ts = str(int(time.time()) + 301)
    secret = "test_slack_secret"
    sig = _slack_sig(body, ts, secret)
    assert _verify_slack_signature(body, ts, sig, secret) is False


def test_slack_wrong_signature():
    body = b'{"event": "test"}'
    ts = str(int(time.time()))
    secret = "test_slack_secret"
    assert _verify_slack_signature(body, ts, "v0=badhash", secret) is False


def test_slack_tampered_body():
    body = b'{"event": "test"}'
    ts = str(int(time.time()))
    secret = "test_slack_secret"
    sig = _slack_sig(body, ts, secret)
    tampered = b'{"event": "tampered"}'
    assert _verify_slack_signature(tampered, ts, sig, secret) is False


# ---------------------------------------------------------------------------
# _verify_github_signature
# ---------------------------------------------------------------------------

def test_github_valid_signature():
    body = b'{"action": "opened"}'
    secret = "github_secret"
    sig = _github_sig(body, secret)
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.github_webhook_secret = secret
        assert _verify_github_signature(body, sig) is True


def test_github_no_secret_configured():
    body = b'{"action": "opened"}'
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.github_webhook_secret = ""
        assert _verify_github_signature(body, "sha256=anything") is False


def test_github_wrong_signature():
    body = b'{"action": "opened"}'
    secret = "github_secret"
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.github_webhook_secret = secret
        assert _verify_github_signature(body, "sha256=badhash") is False


def test_github_tampered_body():
    body = b'{"action": "opened"}'
    secret = "github_secret"
    sig = _github_sig(body, secret)
    tampered = b'{"action": "closed"}'
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.github_webhook_secret = secret
        assert _verify_github_signature(tampered, sig) is False


def test_github_missing_sha256_prefix():
    body = b'{"action": "opened"}'
    secret = "github_secret"
    raw_hex = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.github_webhook_secret = secret
        assert _verify_github_signature(body, raw_hex) is False


# ---------------------------------------------------------------------------
# _verify_clerk_signature
# ---------------------------------------------------------------------------

def test_clerk_no_secret_returns_true():
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.clerk_webhook_secret = ""
        result = _verify_clerk_signature(b'{"type":"user.created"}', {})
    assert result is True


def test_clerk_valid_signature():
    raw_secret = b"clerk_raw_secret_32bytes_padding!"
    b64_secret = "whsec_" + base64.b64encode(raw_secret).decode()
    body = b'{"type":"user.created"}'
    svix_id = "msg_01"
    svix_ts = str(int(time.time()))
    sig = _clerk_sig(svix_id, svix_ts, body, raw_secret)
    headers = {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": sig}
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.clerk_webhook_secret = b64_secret
        assert _verify_clerk_signature(body, headers) is True


def test_clerk_stale_timestamp():
    raw_secret = b"clerk_raw_secret_32bytes_padding!"
    b64_secret = "whsec_" + base64.b64encode(raw_secret).decode()
    body = b'{"type":"user.created"}'
    svix_id = "msg_02"
    svix_ts = str(int(time.time()) - 301)
    sig = _clerk_sig(svix_id, svix_ts, body, raw_secret)
    headers = {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": sig}
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.clerk_webhook_secret = b64_secret
        assert _verify_clerk_signature(body, headers) is False


def test_clerk_wrong_signature():
    raw_secret = b"clerk_raw_secret_32bytes_padding!"
    b64_secret = "whsec_" + base64.b64encode(raw_secret).decode()
    body = b'{"type":"user.created"}'
    svix_ts = str(int(time.time()))
    headers = {
        "svix-id": "msg_03",
        "svix-timestamp": svix_ts,
        "svix-signature": "v1,badsignaturevalue==",
    }
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.clerk_webhook_secret = b64_secret
        assert _verify_clerk_signature(body, headers) is False


def test_clerk_tampered_body():
    raw_secret = b"clerk_raw_secret_32bytes_padding!"
    b64_secret = "whsec_" + base64.b64encode(raw_secret).decode()
    body = b'{"type":"user.created"}'
    svix_id = "msg_04"
    svix_ts = str(int(time.time()))
    sig = _clerk_sig(svix_id, svix_ts, body, raw_secret)
    headers = {"svix-id": svix_id, "svix-timestamp": svix_ts, "svix-signature": sig}
    tampered = b'{"type":"user.deleted"}'
    with patch("app.routers.webhooks.settings") as mock_settings:
        mock_settings.clerk_webhook_secret = b64_secret
        assert _verify_clerk_signature(tampered, headers) is False
