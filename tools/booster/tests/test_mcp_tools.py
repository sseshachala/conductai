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
    # With no embeddings, vector_search_file falls back to keyword match.
    # "authenticate users" has no keyword overlap with "obscure_xyz" → no match.
    content = "def obscure_xyz():\n    pass\n"
    _write(tmp_root, "app/misc.py", content)
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    result = smart_read(tmp_root / "app/misc.py", "authenticate users", ix)
    assert "no matching symbols" in result
    assert "Use Read tool" in result


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


# --- cache-alignment tests ---

from booster.mcp_server import _sort_schema, _provider
import os

def test_sort_schema_top_level():
    schema = {"type": "object", "required": ["x"], "properties": {"x": {"type": "string"}}}
    result = _sort_schema(schema)
    assert list(result.keys()) == sorted(result.keys())

def test_sort_schema_nested():
    schema = {"z": 1, "a": {"q": 2, "b": 3}, "m": [{"z": 1, "a": 2}]}
    result = _sort_schema(schema)
    assert list(result.keys()) == ["a", "m", "z"]
    assert list(result["a"].keys()) == ["b", "q"]
    assert list(result["m"][0].keys()) == ["a", "z"]

def test_provider_explicit_env(monkeypatch):
    monkeypatch.setenv("BOOSTER_PROVIDER", "openai")
    assert _provider() == "openai"

def test_provider_anthropic_key(monkeypatch):
    monkeypatch.delenv("BOOSTER_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _provider() == "anthropic"

def test_provider_openai_key(monkeypatch):
    monkeypatch.delenv("BOOSTER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert _provider() == "openai"

def test_provider_unknown(monkeypatch):
    monkeypatch.delenv("BOOSTER_PROVIDER", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert _provider() == "unknown"

def test_list_tools_sorted():
    import asyncio
    from booster.mcp_server import list_tools
    tools = asyncio.run(list_tools())
    names = [t.name for t in tools]
    assert names == sorted(names), f"tools not sorted: {names}"

def test_list_tools_schema_keys_sorted():
    import asyncio
    from booster.mcp_server import list_tools
    tools = asyncio.run(list_tools())
    for t in tools:
        schema = t.inputSchema
        assert list(schema.keys()) == sorted(schema.keys()), f"{t.name} schema keys not sorted"
