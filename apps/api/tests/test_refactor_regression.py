"""
Refactor regression tests — ensures cleanup PRs don't break behaviour.

Each test is tied to a GH issue. Add a test here whenever a refactor issue is closed.
"""
import re
import pytest


# ── #638 — deleted railway_* and modal_token_* from config ──────────────────

def test_config_no_railway_fields():
    from app.core.config import Settings
    s = Settings()
    for field in ("railway_api_token", "railway_project_id", "railway_environment_id",
                  "railway_backend_service_id", "railway_frontend_service_id"):
        assert not hasattr(s, field), f"Deleted field still on Settings: {field}"


def test_config_no_modal_platform_fields():
    from app.core.config import Settings
    s = Settings()
    for field in ("modal_token_id", "modal_token_secret"):
        assert not hasattr(s, field), f"Deleted field still on Settings: {field}"


# ── #636 — _FORBIDDEN_SHELL_PATTERNS extracted to sandbox_constants ──────────

def test_forbidden_patterns_importable_from_constants():
    from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS
    assert isinstance(_FORBIDDEN_SHELL_PATTERNS, list)
    assert len(_FORBIDDEN_SHELL_PATTERNS) > 0


def test_forbidden_patterns_consistent_across_runners():
    from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS as base
    from app.runtime.sandbox_session import _FORBIDDEN_SHELL_PATTERNS as p1
    from app.runtime.modal_session_runner import _FORBIDDEN_SHELL_PATTERNS as p2
    from app.runtime.e2b_session_runner import _FORBIDDEN_SHELL_PATTERNS as p3
    assert p1 == base, "sandbox_session pattern diverged from constants"
    assert p2 == base, "modal_session_runner pattern diverged from constants"
    assert p3 == base, "e2b_session_runner pattern diverged from constants"


def test_forbidden_patterns_block_dangerous_commands():
    from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS
    dangerous = [
        "rm -rf /",
        "rm -fr /",
        "mkfs.ext4 /dev/sda",
        "dd if=/dev/zero of=/dev/sda",
        ":(){ :|:& };:",
        "> /dev/sdb",
        "chmod 777 /etc",
        "chown root /etc/passwd",
    ]
    for cmd in dangerous:
        matched = any(re.search(p, cmd) for p in _FORBIDDEN_SHELL_PATTERNS)
        assert matched, f"Dangerous command not blocked by any pattern: {cmd!r}"


def test_forbidden_patterns_allow_safe_commands():
    from app.runtime.sandbox_constants import _FORBIDDEN_SHELL_PATTERNS
    safe = [
        "rm -rf ./tmp",
        "ls -la",
        "python3 test.py",
        "git commit -m 'fix'",
        "chmod 755 ./script.sh",
    ]
    for cmd in safe:
        matched = any(re.search(p, cmd) for p in _FORBIDDEN_SHELL_PATTERNS)
        assert not matched, f"Safe command incorrectly blocked: {cmd!r}"
