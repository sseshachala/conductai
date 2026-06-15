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


# ── #637 — merge 3 duplicate LLMClient cost functions into _compute_cost ─────

def test_compute_cost_exists():
    from app.runtime.llm_client import _compute_cost
    assert callable(_compute_cost)


def test_anthropic_cost_delegates_to_compute_cost():
    from app.runtime import llm_client
    # Each thin wrapper must call _compute_cost — verify they return the same value
    from app.runtime.llm_client import LLMUsage, _anthropic_cost, _compute_cost
    u = LLMUsage(input_tokens=1000, output_tokens=500, cache_read_tokens=200, cache_write_tokens=100)
    assert _anthropic_cost("claude-3-5-haiku-20241022", u) == _compute_cost("anthropic", "claude-3-5-haiku-20241022", u)


def test_openai_cost_delegates_to_compute_cost():
    from app.runtime.llm_client import LLMUsage, _openai_cost, _compute_cost
    u = LLMUsage(input_tokens=1000, output_tokens=500)
    assert _openai_cost("gpt-4o-mini", u) == _compute_cost("openai", "gpt-4o-mini", u)


def test_perplexity_cost_delegates_to_compute_cost():
    from app.runtime.llm_client import LLMUsage, _perplexity_cost, _compute_cost
    u = LLMUsage(input_tokens=1000, output_tokens=500)
    assert _perplexity_cost("sonar", u) == _compute_cost("perplexity", "sonar", u)


# ── #635 — merge _run_tests_serial + _run_tests_parallel into _run_tests ─────
# Tests load from source (not the installed wheel) so the refactor is verified before re-publish.

import importlib.util as _ilu
import pathlib as _pl

def _load_cli_main():
    src = _pl.Path(__file__).parents[3] / "packages/conduct-cli/src/conduct_cli/main.py"
    spec = _ilu.spec_from_file_location("conduct_cli_src.main", src)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_run_tests_single_function_exists():
    import inspect
    m = _load_cli_main()
    assert hasattr(m, "_run_tests"), "_run_tests function missing"
    sig = inspect.signature(m._run_tests)
    assert "parallel" in sig.parameters, "_run_tests must have a parallel= kwarg"


def test_run_tests_serial_parallel_removed():
    m = _load_cli_main()
    assert not hasattr(m, "_run_tests_serial"), "_run_tests_serial should be deleted"
    assert not hasattr(m, "_run_tests_parallel"), "_run_tests_parallel should be deleted"
