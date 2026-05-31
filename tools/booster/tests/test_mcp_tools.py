from __future__ import annotations

from pathlib import Path

import pytest

from booster.indexer import SymbolIndexer
from booster.retriever import smart_read
from booster.mcp_server import _route_model


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / ".booster").mkdir()
    return tmp_path


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ── smart_read ─────────────────────────────────────────────────────────────

def test_smart_read_returns_matching_function(tmp_root):
    _write(tmp_root, "app/utils.py", """\
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b

def multiply(a, b):
    return a * b
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = smart_read(tmp_root / "app/utils.py", "add numbers", ix)
    assert "add" in result
    assert "subtract" not in result
    assert "multiply" not in result


def test_smart_read_falls_back_on_no_match(tmp_root):
    content = "def obscure_xyz():\n    pass\n"
    _write(tmp_root, "app/misc.py", content)
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = smart_read(tmp_root / "app/misc.py", "authenticate users", ix)
    assert "obscure_xyz" in result


def test_smart_read_includes_line_header(tmp_root):
    _write(tmp_root, "app/fn.py", "def compute(x):\n    return x * 2\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = smart_read(tmp_root / "app/fn.py", "compute value", ix)
    assert "lines" in result
    assert "compute" in result


def test_smart_read_ts_file(tmp_root):
    _write(tmp_root, "src/auth.ts", """\
function login(user: string, pass: string): boolean {
    return true;
}

function buildReport(): string {
    return 'report';
}
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = smart_read(tmp_root / "src/auth.ts", "login user", ix)
    assert "login" in result
    assert "buildReport" not in result


# ── route_model ────────────────────────────────────────────────────────────

def test_route_haiku_narrow(tmp_root):
    _write(tmp_root, "app/fn.py", "def add(a, b): return a + b\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = _route_model(ix, "fix typo in error message", [])
    assert result["model"] == "haiku"
    assert "reason" in result


def test_route_opus_keyword_refactor(tmp_root):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, "refactor the auth middleware", [])
    assert result["model"] == "opus"
    assert "refactor" in result["reason"]


def test_route_opus_keyword_security(tmp_root):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, "security audit of payment flow", [])
    assert result["model"] == "opus"


def test_route_opus_keyword_architect(tmp_root):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, "architect the new plugin system", [])
    assert result["model"] == "opus"


def test_route_opus_many_files(tmp_root):
    ix = SymbolIndexer(tmp_root)
    files = ["a.py", "b.py", "c.py", "d.py", "e.py"]
    result = _route_model(ix, "update logging", files)
    assert result["model"] == "opus"
    assert "5 files" in result["reason"]


def test_route_sonnet_moderate_files(tmp_root):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, "update user profile handler", ["users.py", "profile.py"])
    assert result["model"] == "sonnet"
    assert "2 files" in result["reason"]


def test_route_returns_reason(tmp_root):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, "migrate database schema", [])
    assert "reason" in result
    assert len(result["reason"]) > 0


@pytest.mark.parametrize("keyword", ["refactor", "architect", "design", "migrate", "security", "audit"])
def test_route_opus_all_keywords(tmp_root, keyword):
    ix = SymbolIndexer(tmp_root)
    result = _route_model(ix, f"{keyword} the system", [])
    assert result["model"] == "opus"
