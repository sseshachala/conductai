"""
Refactor regression tests — ensures cleanup PRs don't break behaviour.

Each test is tied to a GH issue. Add a test here whenever a refactor issue is closed.
"""
import re
import pytest



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



# ── #635 — merge _run_tests_serial + _run_tests_parallel into _run_tests ─────
# Tests load from source (not the installed wheel) so the refactor is verified before re-publish.

import importlib.util as _ilu
import pathlib as _pl

def _load_cli_main():
    import sys as _sys
    cli_src = _pl.Path(__file__).parents[3] / "packages/conduct-cli/src"
    if str(cli_src) not in _sys.path:
        _sys.path.insert(0, str(cli_src))
    src = cli_src / "conduct_cli/main.py"
    spec = _ilu.spec_from_file_location("conduct_cli.main", src)
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
