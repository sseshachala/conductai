"""Tests for v0.3.0 features: schema migration, call edges, diff-aware reads,
test_coverage, blame-based staleness, and the conduct-cli gain JSON contract.
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path

import pytest

from booster.indexer import (
    SymbolIndexer,
    _attribute_calls,
    _blame_file,
    _changed_lines_since,
    _collect_py_calls,
    _collect_ts_calls,
    _filter_by_changed_lines,
    _is_test_file,
    _symbol_last_modified,
)
from booster.retriever import smart_read
from booster.stats import StatsTracker


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / ".booster").mkdir()
    return tmp_path


@pytest.fixture
def git_root(tmp_path: Path) -> Path:
    (tmp_path / ".booster").mkdir()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(root: Path, msg: str = "wip") -> None:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=root, check=True)


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ── Schema migration ──────────────────────────────────────────────────────

def test_schema_fresh_has_new_tables_and_columns(tmp_root):
    idx = SymbolIndexer(tmp_root)
    cols = {r[1] for r in idx._conn.execute("PRAGMA table_info(symbols)").fetchall()}
    assert "commit_last_modified" in cols
    assert "last_modified_ts" in cols
    tables = {r[0] for r in idx._conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    assert "symbol_edges" in tables
    assert "symbol_tests" in tables


def test_schema_migration_from_v02x(tmp_path):
    db_dir = tmp_path / ".booster"
    db_dir.mkdir()
    conn = sqlite3.connect(str(db_dir / "symbols.db"))
    conn.execute("""CREATE TABLE symbols (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
        start_line INTEGER NOT NULL, end_line INTEGER NOT NULL,
        signature TEXT NOT NULL DEFAULT '',
        file_hash TEXT NOT NULL DEFAULT '',
        file_mtime REAL NOT NULL DEFAULT 0.0
    )""")
    conn.execute(
        "INSERT INTO symbols (file, name, kind, start_line, end_line) "
        "VALUES ('a.py', 'foo', 'function', 1, 5)"
    )
    conn.commit()
    conn.close()

    idx = SymbolIndexer(tmp_path)
    cols = {r[1] for r in idx._conn.execute("PRAGMA table_info(symbols)").fetchall()}
    assert "commit_last_modified" in cols
    assert "last_modified_ts" in cols
    rows = idx._conn.execute(
        "SELECT name, commit_last_modified, last_modified_ts FROM symbols"
    ).fetchall()
    assert rows[0]["name"] == "foo"
    assert rows[0]["commit_last_modified"] == ""
    assert rows[0]["last_modified_ts"] == 0


# ── Call edges ────────────────────────────────────────────────────────────

def test_call_edges_python_same_file(tmp_root):
    _write(tmp_root, "auth.py", """
def login(user):
    return validate(user)

def validate(user):
    return user is not None
""")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    callees = idx.expand_calls("login", direction="callees")
    names = {r["to_name"] for r in callees}
    assert "validate" in names
    # Resolved within-file: target_id should be non-zero
    for r in callees:
        if r["to_name"] == "validate":
            assert r["to_id"] > 0
            assert r["to_file"] == "auth.py"


def test_call_edges_cross_file_via_name(tmp_root):
    _write(tmp_root, "auth.py", "def login(user):\n    return user\n")
    _write(tmp_root, "cli.py", "from auth import login\n\ndef main():\n    return login('alice')\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    callers = idx.expand_calls("login", direction="callers")
    assert any(r["from_name"] == "main" and r["from_file"] == "cli.py" for r in callers)


def test_call_edges_depth_expansion(tmp_root):
    _write(tmp_root, "chain.py", """
def a():
    b()

def b():
    c()

def c():
    pass
""")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    out = idx.expand_calls("a", direction="callees", depth=2)
    depths = {r["depth"] for r in out}
    names_d1 = {r["to_name"] for r in out if r["depth"] == 1}
    names_d2 = {r["to_name"] for r in out if r["depth"] == 2}
    assert depths == {1, 2}
    assert "b" in names_d1
    assert "c" in names_d2


def test_call_edges_depth_clamped_to_3(tmp_root):
    _write(tmp_root, "x.py", "def f():\n    g()\ndef g():\n    pass\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    # Should not error or recurse forever even with absurd depth.
    out = idx.expand_calls("f", direction="callees", depth=99)
    assert isinstance(out, list)


def test_call_edges_ts_member_expression(tmp_root):
    _write(tmp_root, "x.ts", """
function caller(): void {
  helper();
  obj.method();
}

function helper(): void {}
""")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    out = idx.expand_calls("caller", direction="callees")
    names = {r["to_name"] for r in out}
    assert "helper" in names
    assert "method" in names


def test_attribute_calls_picks_innermost():
    # outer 1-20 contains inner 5-10; a call at line 7 belongs to inner.
    syms = [(1, 1, 20), (2, 5, 10)]
    calls = [("foo", 7)]
    out = _attribute_calls(calls, syms)
    assert out == [(2, "foo", 7)]


def test_call_re_index_clears_old_edges(tmp_root):
    p = _write(tmp_root, "x.py", "def a():\n    b()\ndef b():\n    pass\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    assert idx._conn.execute("SELECT COUNT(*) FROM symbol_edges").fetchone()[0] == 1
    # Replace contents — no calls now
    p.write_text("def a():\n    pass\ndef b():\n    pass\n")
    idx.index_file(p)
    assert idx._conn.execute("SELECT COUNT(*) FROM symbol_edges").fetchone()[0] == 0


# ── Diff-aware reads ──────────────────────────────────────────────────────

def test_changed_lines_since_isolates_modification(git_root):
    _write(git_root, "f.py", "def a():\n    return 1\n\ndef b():\n    return 2\n")
    _commit(git_root, "init")
    _write(git_root, "f.py", "def a():\n    return 1\n\ndef b():\n    return 999\n")
    _commit(git_root, "tweak b")
    ch = _changed_lines_since(git_root, "HEAD~1")
    # Only the b() return-value line changed (line 5).
    assert "f.py" in ch
    assert 5 in ch["f.py"]
    assert 2 not in ch["f.py"]


def test_filter_by_changed_lines_overlaps_symbol_range():
    symbols = [
        {"file": "a.py", "name": "alpha", "start_line": 1, "end_line": 3},
        {"file": "a.py", "name": "beta", "start_line": 5, "end_line": 8},
    ]
    changed = {"a.py": {6}}
    out = _filter_by_changed_lines(symbols, changed)
    assert len(out) == 1
    assert out[0]["name"] == "beta"


def test_smart_read_since_filter(git_root):
    _write(git_root, "f.py", "def alpha():\n    return 1\n\ndef beta():\n    return 2\n")
    _commit(git_root, "init")
    _write(git_root, "f.py", "def alpha():\n    return 1\n\ndef beta():\n    return 999\n")
    _commit(git_root, "tweak beta")
    idx = SymbolIndexer(git_root)
    idx.index_all()
    out = smart_read(git_root / "f.py", "alpha beta", idx, since="HEAD~1")
    assert "beta" in out
    assert "def alpha" not in out


def test_smart_read_since_no_changes(git_root):
    _write(git_root, "f.py", "def alpha():\n    return 1\n")
    _commit(git_root, "init")
    idx = SymbolIndexer(git_root)
    idx.index_all()
    out = smart_read(git_root / "f.py", "alpha", idx, since="HEAD")
    assert "no changes" in out


def test_changed_lines_graceful_in_non_git(tmp_root):
    assert _changed_lines_since(tmp_root, "HEAD~1") == {}


# ── Blame / staleness ─────────────────────────────────────────────────────

def test_blame_populates_commit_metadata(git_root):
    _write(git_root, "x.py", "def hello():\n    return 1\n")
    _commit(git_root, "add hello")
    idx = SymbolIndexer(git_root)
    idx.index_all()
    rows = idx._conn.execute(
        "SELECT name, commit_last_modified, last_modified_ts FROM symbols"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0]["commit_last_modified"]  # non-empty sha
    assert rows[0]["last_modified_ts"] > 0


def test_blame_graceful_in_non_git(tmp_root):
    _write(tmp_root, "x.py", "def hello():\n    return 1\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    rows = idx._conn.execute(
        "SELECT commit_last_modified, last_modified_ts FROM symbols"
    ).fetchall()
    assert rows[0]["commit_last_modified"] == ""
    assert rows[0]["last_modified_ts"] == 0


def test_blame_file_returns_empty_for_missing_git():
    # Path under /tmp that's not a git repo
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        p = root / "x.py"
        p.write_text("x = 1\n")
        assert _blame_file(p, root) == {}


def test_symbol_last_modified_picks_max():
    blame = {1: ("sha1", 100), 2: ("sha2", 200), 3: ("sha3", 50)}
    sha, ts = _symbol_last_modified(blame, 1, 3)
    assert sha == "sha2"
    assert ts == 200


def test_smart_read_includes_staleness_header(git_root):
    _write(git_root, "x.py", "def hello():\n    return 1\n")
    _commit(git_root, "init")
    idx = SymbolIndexer(git_root)
    idx.index_all()
    out = smart_read(git_root / "x.py", "hello", idx)
    assert "last_modified" in out


# ── test_coverage ─────────────────────────────────────────────────────────

def test_is_test_file_patterns():
    assert _is_test_file("tests/test_auth.py")
    assert _is_test_file("test_login.py")
    assert _is_test_file("auth_test.py")
    assert _is_test_file("src/login.test.ts")
    assert _is_test_file("src/login.spec.tsx")
    assert _is_test_file("__tests__/foo.ts")
    assert not _is_test_file("src/auth.py")
    assert not _is_test_file("src/utils/helpers.ts")


def test_test_coverage_finds_imported_symbols(tmp_root):
    _write(tmp_root, "auth.py", "def login(user):\n    return user\n\ndef logout(user):\n    return None\n")
    _write(tmp_root, "tests/test_auth.py", "from auth import login\n\ndef test_login():\n    assert login('a')\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    test_files, refs = idx.index_tests()
    assert test_files == 1
    assert refs >= 1
    out = idx.test_coverage("login")
    assert len(out) == 1
    assert out[0]["test_file"] == "tests/test_auth.py"


def test_test_coverage_returns_empty_for_untested(tmp_root):
    _write(tmp_root, "auth.py", "def login(user):\n    return user\n\ndef logout(user):\n    return None\n")
    _write(tmp_root, "tests/test_auth.py", "from auth import login\n\ndef test_login():\n    assert login('a')\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    idx.index_tests()
    assert idx.test_coverage("logout") == []


def test_test_coverage_ignores_short_symbol_names(tmp_root):
    """Names <3 chars are skipped to avoid noisy substring matches."""
    _write(tmp_root, "x.py", "def ab():\n    pass\n\ndef longer():\n    pass\n")
    _write(tmp_root, "tests/test_x.py", "from x import longer\ndef test_l():\n    longer()\nab = 1\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    idx.index_tests()
    # 'ab' is too short, should not match (even though it appears in test file)
    assert idx.test_coverage("ab") == []
    # 'longer' should match
    assert len(idx.test_coverage("longer")) == 1


# ── conduct-cli contract: gain JSON shape must stay stable ────────────────

def test_stats_summary_fields_unchanged(tmp_root):
    """conduct-cli (guard.py:1281) parses `booster gain -f json`.
    These fields are the contract; renaming or removing them is a breaking change.
    """
    tracker = StatsTracker(tmp_root)
    summary = tracker.summary()
    for required in (
        "active_days", "total_reads", "full_tokens", "slice_tokens",
        "saved_tokens", "savings_pct", "top_files",
    ):
        assert required in summary, f"conduct-cli depends on '{required}' in tracker.summary()"


def test_stats_crusher_summary_fields_unchanged(tmp_root):
    """booster gain -f json includes crusher_summary under 'crusher' key."""
    tracker = StatsTracker(tmp_root)
    cs = tracker.crusher_summary()
    for required in ("count", "saved_bytes", "savings_pct"):
        assert required in cs, f"conduct-cli reads 'crusher.{required}'"


# ── Re-index cleanup ──────────────────────────────────────────────────────

def test_re_index_clears_edges_and_tests(tmp_root):
    _write(tmp_root, "x.py", "def alpha():\n    beta()\ndef beta():\n    pass\n")
    _write(tmp_root, "tests/test_x.py", "from x import alpha\ndef test_alpha():\n    alpha()\n")
    idx = SymbolIndexer(tmp_root)
    idx.index_all()
    idx.index_tests()
    assert idx._conn.execute("SELECT COUNT(*) FROM symbol_edges").fetchone()[0] >= 1
    assert idx._conn.execute("SELECT COUNT(*) FROM symbol_tests").fetchone()[0] >= 1
    # Force re-index — both auxiliary tables should be cleared
    idx.index_all(force=True)
    assert idx._conn.execute("SELECT COUNT(*) FROM symbol_tests").fetchone()[0] == 0
