"""Tests for signed policy (#855-A) and fail-mode meta-rule (#855-C).

Functions under test now live in conduct_cli.hooks.pretooluse;
shared constants (SIGNING_KEY_PATH, etc.) live in conduct_cli.hooks.base.
Patch targets follow Python's import-time binding rules:
  - Constants used inside pretooluse functions → patch on `pre`
  - Constants used inside base functions (load_config) → patch on `base`
"""
from __future__ import annotations
import hashlib
import hmac
import json
import time
from contextlib import ExitStack, contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import conduct_cli.hooks.base as base
import conduct_cli.hooks.pretooluse as pre


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_key() -> tuple[bytes, str]:
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


# ── _verify_policy_signature ──────────────────────────────────────────────────

def _patch_verify(tmp_path, key_path):
    """Patch both SIGNING_KEY_PATH and GUARD_DIR so path-traversal check passes."""
    return (
        patch.object(pre, "SIGNING_KEY_PATH", key_path),
        patch.object(pre, "GUARD_DIR", tmp_path),
    )


def test_verify_passes_with_valid_signature(tmp_path):
    key_bytes, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": []}
    policy["signature"] = _sign_policy(policy, key_bytes)

    with _ctx(*_patch_verify(tmp_path, key_path)):
        assert pre._verify_policy_signature(policy) is True


def test_verify_fails_with_wrong_signature(tmp_path):
    _, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": [], "signature": "badbadbadbad"}

    with _ctx(*_patch_verify(tmp_path, key_path)):
        assert pre._verify_policy_signature(policy) is False


def test_verify_fails_when_signature_missing_and_key_present(tmp_path):
    _, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": []}  # no "signature" key

    with _ctx(*_patch_verify(tmp_path, key_path)):
        assert pre._verify_policy_signature(policy) is False


def test_verify_passes_when_no_key_file(tmp_path):
    """No signing.key → dev mode, always allow."""
    key_path = tmp_path / "signing.key"  # does not exist
    policy = {"version": "v1", "rules": [], "signature": "anything"}

    with _ctx(*_patch_verify(tmp_path, key_path)):
        assert pre._verify_policy_signature(policy) is True


def test_verify_strips_signature_and_signed_at_before_computing(tmp_path):
    key_bytes, key_hex = _make_key()
    key_path = _write_key(tmp_path, key_hex)
    policy = {"version": "v1", "rules": [], "signed_at": "2026-01-01T00:00:00Z"}
    policy["signature"] = _sign_policy(policy, key_bytes)
    policy["signed_at"] = "2030-12-31T00:00:00Z"  # mutated after signing

    with _ctx(*_patch_verify(tmp_path, key_path)):
        assert pre._verify_policy_signature(policy) is True


# ── _maybe_sync_policy ────────────────────────────────────────────────────────

def _setup_sync(tmp_path, local_policy, remote_policy, key_hex=None):
    """Wire _maybe_sync_policy with mocked HTTP + config + paths."""
    config_path   = tmp_path / "config.json"
    policy_path   = tmp_path / "policy.json"
    version_cache = tmp_path / "version_cache.json"

    config_path.write_text(json.dumps({
        "workspace_id": "ws-1",
        "api_key": "tok",
        "api_url": "https://api.test",
    }))
    if local_policy is not None:
        policy_path.write_text(json.dumps(local_policy))

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(remote_policy).encode()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)

    signing_key_path = tmp_path / "signing.key"
    if key_hex:
        signing_key_path.write_text(key_hex)

    patches = [
        patch.object(base, "CONFIG_PATH", config_path),         # for load_config()
        patch.object(pre, "active_policy_path", return_value=policy_path),
        patch.object(pre, "VERSION_CACHE_PATH", version_cache),
        patch.object(pre, "SIGNING_KEY_PATH", signing_key_path),
        patch.object(pre, "GUARD_DIR", tmp_path),               # for path-traversal check
        patch("urllib.request.urlopen", return_value=mock_resp),
        patch.object(pre, "_daemon_alive", return_value=False),
        patch("subprocess.Popen"),  # suppress _post_signature_invalid_event side-effect
    ]
    return policy_path, patches


def test_sync_rejects_tampered_policy(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "signature": "badhash"}

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    assert json.loads(policy_path.read_text())["version"] == "v1"


def test_sync_accepts_valid_signed_policy(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    assert json.loads(policy_path.read_text())["version"] == "v2"


def test_failmode_downgrade_blocked_without_token(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
              "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed"
    assert saved["version"] == "v1"


def test_failmode_downgrade_blocked_with_wrong_token(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
              "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open",
              "fail_mode_downgrade_token": "wrong-token"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed"
    assert saved["version"] == "v1"


def test_failmode_downgrade_allowed_with_correct_token(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_closed",
              "fail_mode_downgrade_token": "secret-abc"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_open",
              "fail_mode_downgrade_token": "secret-abc"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_open"
    assert saved["version"] == "v2"


def test_failmode_open_to_closed_always_allowed(tmp_path):
    key_bytes, key_hex = _make_key()
    local  = {"version": "v1", "rules": [], "fail_mode": "fail_open"}
    remote = {"version": "v2", "rules": [], "fail_mode": "fail_closed"}
    remote["signature"] = _sign_policy(remote, key_bytes)

    policy_path, patches = _setup_sync(tmp_path, local, remote, key_hex)
    with _ctx(*patches):
        pre._maybe_sync_policy()

    saved = json.loads(policy_path.read_text())
    assert saved["fail_mode"] == "fail_closed"
    assert saved["version"] == "v2"


# ── helper ────────────────────────────────────────────────────────────────────

@contextmanager
def _ctx(*cms):
    with ExitStack() as stack:
        for cm in cms:
            stack.enter_context(cm)
        yield
