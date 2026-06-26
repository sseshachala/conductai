"""Tests for #855-A (signed policy) and #855-C (fail-mode meta-rule)."""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import conduct_cli.hook_template as ht


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_key() -> tuple[bytes, str]:
    """Return (key_bytes, hex_string) for a fresh signing key."""
    key = b"deadbeef" * 4  # 32 bytes
    return key, key.hex()


def _sign_policy(policy: dict, key_bytes: bytes) -> str:
    body = {k: v for k, v in policy.items() if k not in ("signature", "signed_at")}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key_bytes, canonical.encode(), hashlib.sha256).hexdigest()


def _write_key(tmp_path: Path, key_hex: str) -> Path:
    p = tmp_path / "signing.key"
    p.write_text(key_hex)
    return p


# ── #855-A: _verify_policy_signature ─────────────────────────────────────────

def test_verify_passes_with_valid_signature(tmp_path):
    key_bytes, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": []}
    policy["signature"] = _sign_policy(policy, key_bytes)

    with (
        patch.object(ht, "SIGNING_KEY_PATH", key_path),
        patch.object(ht, "GUARD_DIR", tmp_path),
    ):
        assert ht._verify_policy_signature(policy) is True


def test_verify_fails_with_wrong_signature(tmp_path):
    _, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": [], "signature": "badbadbadbad"}

    with (
        patch.object(ht, "SIGNING_KEY_PATH", key_path),
        patch.object(ht, "GUARD_DIR", tmp_path),
    ):
        assert ht._verify_policy_signature(policy) is False


def test_verify_fails_when_signature_missing_and_key_present(tmp_path):
    _, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": []}  # no "signature" key

    with (
        patch.object(ht, "SIGNING_KEY_PATH", key_path),
        patch.object(ht, "GUARD_DIR", tmp_path),
    ):
        assert ht._verify_policy_signature(policy) is False


def test_verify_passes_when_no_key_file(tmp_path):
    """No signing.key → dev mode, always allow."""
    key_path = tmp_path / "signing.key"  # does not exist
    policy = {"version": "v1", "rules": [], "signature": "anything"}

    with (
        patch.object(ht, "SIGNING_KEY_PATH", key_path),
        patch.object(ht, "GUARD_DIR", tmp_path),
    ):
        assert ht._verify_policy_signature(policy) is True


def test_verify_strips_signature_and_signed_at_before_computing(tmp_path):
    """signed_at and signature fields must not be part of the signed body."""
    key_bytes, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": [], "signed_at": "2026-01-01T00:00:00Z"}
    policy["signature"] = _sign_policy(policy, key_bytes)
    # Add a different signed_at — should still verify because it's excluded from body
    policy["signed_at"] = "2030-12-31T00:00:00Z"

    with (
        patch.object(ht, "SIGNING_KEY_PATH", key_path),
        patch.object(ht, "GUARD_DIR", tmp_path),
    ):
        assert ht._verify_policy_signature(policy) is True


# ── #855-C: fail-mode meta-rule in _maybe_sync_policy ────────────────────────

def _setup_sync(tmp_path, local_policy, remote_policy, key_hex=None):
    """
    Wire up _maybe_sync_policy with mocked HTTP + config + paths.
    Returns the path objects so callers can assert on POLICY_PATH.
    """
    config_path = tmp_path / "config.json"
    policy_path = tmp_path / "policy.json"
    version_cache = tmp_path / "version_cache.json"

    config_path.write_text(json.dumps({
        "workspace_id": "ws-1",
        "api_key": "tok",
        "api_url": "https://api.test",
    }))
    if local_policy is not None:
        policy_path.write_text(json.dumps(local_policy))

    # Mock urllib so "remote" is returned without a real HTTP call
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(remote_policy).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    patches = [
        patch.object(ht, "CONFIG_PATH", config_path),
        patch.object(ht, "POLICY_PATH", policy_path),
        patch.object(ht, "VERSION_CACHE_PATH", version_cache),
        patch.object(ht, "SIGNING_KEY_PATH", tmp_path / "signing.key"),
        patch.object(ht, "GUARD_DIR", tmp_path),
        patch("urllib.request.urlopen", return_value=mock_resp),
        patch.object(ht, "_daemon_alive", return_value=False),
        # Disable journal side-effect from _post_signature_invalid_event
        patch("subprocess.Popen"),
    ]
    if key_hex:
        (tmp_path / "signing.key").write_text(key_hex)

    return policy_path, patches


def test_sync_rejects_tampered_policy(tmp_path):
    """Tampered remote policy (bad sig) must not overwrite local policy."""
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "signature": "badhash"}

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["version"] == "v1", "tampered remote should not replace local policy"


def test_sync_accepts_valid_signed_policy(tmp_path):
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["version"] == "v2"


def test_failmode_downgrade_blocked_without_token(tmp_path):
    """fail_closed → fail_open must be rejected if no downgrade token matches."""
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
             "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed", "downgrade without token must be rejected"
    assert saved["version"] == "v1"


def test_failmode_downgrade_blocked_with_wrong_token(tmp_path):
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
             "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open",
              "fail_mode_downgrade_token": "wrong-token"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed"
    assert saved["version"] == "v1"


def test_failmode_downgrade_allowed_with_correct_token(tmp_path):
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
             "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open",
              "fail_mode_downgrade_token": "secret-abc"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_open"
    assert saved["version"] == "v2"


def test_failmode_open_to_closed_always_allowed(tmp_path):
    """Upgrading to fail_closed needs no token — only downgrade is gated."""
    key_bytes, key_hex = _make_key()
    local = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_closed"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        ht._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed"
    assert saved["version"] == "v2"


# ── tiny helper so we can unpack a list of context managers ──────────────────

from contextlib import contextmanager, ExitStack

@contextmanager
def _ctx(*cms):
    with ExitStack() as stack:
        for cm in cms:
            stack.enter_context(cm)
        yield
