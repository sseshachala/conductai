#!/usr/bin/env python3
"""
CI gate: no new test file may adopt the sys.modules-stub anti-pattern.

## The anti-pattern

Test files that do this at module-import time:

    sys.modules.setdefault("app.core.config", _cfg_stub)
    sys.modules.setdefault("app.core.database", MagicMock())
    del sys.modules["app.core.auth"]

...pollute every subsequent test file that runs after them. FastAPI's `app`
holds captured references to functions from the OLD (torn-down) modules;
subsequent tests that hit the app's routes get contaminated router state and
fail with opaque 500s. This bit us for months (~13 CI failures) until #1373
cleaned two files and #1317/#1318 closed the specific incidents.

## Why a ratchet, not a full cleanup

10 pre-existing files (allowlisted below) legitimately use this pattern to
mock SQLAlchemy or stub infrastructure that can't be imported cleanly.
Removing them requires rewriting each test file's body — ~25 hrs of work
across the 10 files, blocking other value-shipping. See epic #1075.

This gate prevents any NEW test file from adopting the pattern. The 10
existing files continue to work; when a file is properly rewritten, remove
it from ALLOWLIST.

## Failure mode

Any test file under apps/api/tests/ that contains ONE OF:
- `sys.modules.setdefault(...app.core.*...)` or `sys.modules.setdefault(...app.models.*...)`
- `sys.modules[...app.core.*...] = ...`
- `del sys.modules[...app.core.*...]` at MODULE level (not inside a fixture)

...fails CI unless the file path is in ALLOWLIST.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # apps/api/
TESTS = ROOT / "tests"

# Files that use the anti-pattern today. Removing an entry means the file
# has been rewritten to use per-test monkeypatch / dep overrides / real
# modules instead of module-level sys.modules stubs.
#
# Epic: #1075. Progress: #1373 removed 2 files (test_agent_identity_auth,
# test_token_paths) and closed #1317 + #1318.
ALLOWLIST = {
    "tests/test_analytics_dora.py",
    "tests/test_analytics_scorecards.py",
    "tests/test_guard.py",
    "tests/test_guard_events_api.py",
    "tests/test_guard_policy_engine.py",
    "tests/test_guard_savings.py",
    "tests/test_guard_spend_month_window.py",
    "tests/test_llm_cache_integration.py",
    # tests/test_session_reports.py — removed from allowlist 2026-08-28,
    # rewritten to import real modules directly (env vars + skipif on DB).
    "tests/test_team_os.py",
    "tests/test_token_paths.py",
    "tests/test_workspace_seed.py",
    "tests/test_z_executor_lifecycle.py",
}

# Match:
#   sys.modules[".app.core..."] = ...
#   sys.modules.setdefault(".app.core.*." or ".app.models.*.", ...)
#   del sys.modules[".app.core.*."]
#   sys.modules.pop(".app.core.*.", ...)
_PATTERNS = [
    re.compile(r"""sys\.modules\[["']app\.(core|models|modules|runtime|routers)"""),
    re.compile(r"""sys\.modules\.setdefault\(["']app\.(core|models|modules|runtime|routers)"""),
    re.compile(r"""del\s+sys\.modules\[["']app\.(core|models|modules|runtime|routers)"""),
    re.compile(r"""sys\.modules\.pop\(["']app\.(core|models|modules|runtime|routers)"""),
]


def scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    try:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for pat in _PATTERNS:
                if pat.search(line):
                    hits.append((lineno, stripped[:100]))
                    break
    except (OSError, UnicodeDecodeError):
        pass
    return hits


def main() -> int:
    if not TESTS.is_dir():
        print(f"ERROR: {TESTS} not found — run from apps/api/", file=sys.stderr)
        return 2

    violations: dict[str, list[tuple[int, str]]] = {}
    for path in sorted(TESTS.rglob("test_*.py")):
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWLIST:
            continue
        hits = scan(path)
        if hits:
            violations[rel] = hits

    if not violations:
        print(
            f"sys.modules ratchet OK — {len(ALLOWLIST)} allowlisted files, "
            "no new adopters."
        )
        return 0

    print(
        "\nSYS.MODULES ANTI-PATTERN — new test files must not stub app.* modules:",
        file=sys.stderr,
    )
    for path, hits in violations.items():
        print(f"\n  ✗  {path}", file=sys.stderr)
        for lineno, line in hits[:3]:
            print(f"      line {lineno}: {line}", file=sys.stderr)
        if len(hits) > 3:
            print(f"      ... +{len(hits) - 3} more matches", file=sys.stderr)
    print(
        "\nSee epic #1075. Fix pattern: use monkeypatch/mock.patch per-test, "
        "or app.dependency_overrides for FastAPI deps.",
        file=sys.stderr,
    )
    print(
        "If this file MUST use the pattern (rare), add it to ALLOWLIST in "
        "scripts/check_sys_modules_ratchet.py with a comment explaining why.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
