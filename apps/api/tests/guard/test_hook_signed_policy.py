"""Unit tests for signed-policy enforcement in the ConductGuard CLI hook.

These tests exercise _verify_policy_signature and the audit-event emission path
without any network or DB calls. They run against an in-memory temp directory
that mimics ~/.conductguard/.

Test matrix:
  1. Valid signature   -> accepted, no audit event fired
  2. Tampered body     -> rejected, audit event emitted
  3. No signing.key    -> no-op (dev mode), policy accepted
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import tempfile
import types
import unittest.mock
from pathlib import Path

import pytest

# ── Minimal env so any transitive Settings() import doesn't blow up ──────────
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_key() -> bytes:
    return os.urandom(32)


def _sign_policy(policy_dict: dict, key_bytes: bytes) -> str:
    """Produce the HMAC-SHA256 hex signature the server would compute."""
    body = {k: v for k, v in policy_dict.items() if k not in ("signature", "signed_at")}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hmac.new(key_bytes, canonical.encode(), hashlib.sha256).hexdigest()


def _make_policy(rules: list | None = None) -> dict:
    return {
        "workspace_id": "test-ws",
        "version": "2026-06-25T00:00:00Z-abc123",
        "persona": "standard",
        "fail_mode": "fail_open",
        "rules": rules or [],
    }


def _load_hook_module(guard_dir: Path):
    """Import hook_template.py with GUARD_DIR / paths patched to tmp dir."""
    import importlib.util

    hook_path = (
        Path(__file__).resolve().parent.parent.parent.parent.parent
        / "packages/conduct-cli/src/conduct_cli/hook_template.py"
    )
    spec = importlib.util.spec_from_file_location("hook_template", hook_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Patch constants AFTER exec so the module's global bindings are overridden.
    module.GUARD_DIR        = guard_dir
    module.POLICY_PATH      = guard_dir / "policy.json"
    module.CONFIG_PATH      = guard_dir / "config.json"
    module.SIGNING_KEY_PATH = guard_dir / "signing.key"

    # Stub subprocess to capture Popen calls.
    # Mock the Popen class itself so .assert_not_called() works on the class.
    mock_popen = unittest.mock.MagicMock()
    mock_subprocess = types.SimpleNamespace(Popen=mock_popen, DEVNULL=-1)
    module.subprocess = mock_subprocess

    return module


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_valid_signature_accepted():
    """Policy signed with the correct key passes verification."""
    with tempfile.TemporaryDirectory() as tmp:
        guard_dir = Path(tmp)
        key = _make_key()

        # Write signing key
        (guard_dir / "signing.key").write_text(key.hex())

        # Build a signed policy
        policy = _make_policy(rules=[{"rule_id": "no-rm", "match_pattern": "rm -rf", "action": "block"}])
        policy["signature"] = _sign_policy(policy, key)
        policy["signed_at"]  = "2026-06-25T00:00:00Z"

        module = _load_hook_module(guard_dir)

        result = module._verify_policy_signature(policy)
        assert result is True, "Valid signature should be accepted"

        # Confirm Popen (audit event) was NOT called
        module.subprocess.Popen.assert_not_called()


def test_tampered_signature_rejected_and_audit_emitted():
    """Policy with tampered body fails verification and emits a policy_signature_invalid event."""
    with tempfile.TemporaryDirectory() as tmp:
        guard_dir = Path(tmp)
        key = _make_key()
        (guard_dir / "signing.key").write_text(key.hex())

        # Write a valid guard config so _post_signature_invalid_event can resolve workspace_id
        (guard_dir / "config.json").write_text(json.dumps({
            "workspace_id": "ws-test-123",
            "user_email": "dev@example.com",
            "api_url": "https://api.conductai.ai",
        }))

        # Build original policy and sign it
        policy = _make_policy(rules=[{"rule_id": "allow-all", "action": "audit"}])
        policy["signature"] = _sign_policy(policy, key)
        policy["signed_at"]  = "2026-06-25T00:00:00Z"

        # Tamper: inject a deny-all rule after signing
        policy["rules"].append({"rule_id": "deny-all", "action": "block", "match_pattern": ".*"})

        module = _load_hook_module(guard_dir)

        # (a) Signature check must fail
        result = module._verify_policy_signature(policy)
        assert result is False, "Tampered policy should fail verification"

        # (b) Emitting the audit event should attempt a Popen call
        module._post_signature_invalid_event(
            expected_sig=policy.get("signature"),
            computed_sig=None,
            policy_version=policy.get("version"),
            hostname="test-host",
        )
        module.subprocess.Popen.assert_called_once()

        # Inspect the audit payload embedded in the Popen script
        call_kwargs = module.subprocess.Popen.call_args
        script_arg  = call_kwargs[0][0][2]  # [sys.executable, "-c", script]
        assert "policy_signature_invalid" in script_arg
        assert "ws-test-123" in script_arg


def test_missing_signing_key_is_no_op():
    """Without a signing.key file the hook accepts unsigned policies (backwards compat)."""
    with tempfile.TemporaryDirectory() as tmp:
        guard_dir = Path(tmp)
        # No signing.key written

        policy = _make_policy(rules=[{"rule_id": "allow-all", "action": "audit"}])
        # No signature field

        module = _load_hook_module(guard_dir)

        result = module._verify_policy_signature(policy)
        assert result is True, "Missing signing key should be a no-op (return True)"

        module.subprocess.Popen.assert_not_called()
