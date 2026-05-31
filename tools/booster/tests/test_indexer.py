from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from booster.indexer import SymbolIndexer


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / ".booster").mkdir()
    return tmp_path


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ── Python indexing ────────────────────────────────────────────────────────

def test_py_functions(tmp_root):
    _write(tmp_root, "app/utils.py", """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("app/utils.py")
    names = {s["name"] for s in syms}
    assert names == {"add", "subtract"}
    assert all(s["kind"] == "function" for s in syms)


def test_py_class(tmp_root):
    _write(tmp_root, "app/models.py", """
class User:
    def __init__(self, name):
        self.name = name

    def greet(self):
        return f"Hello {self.name}"
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("app/models.py")
    kinds = {s["kind"] for s in syms}
    assert "class" in kinds
    assert "function" in kinds
    assert "User" in {s["name"] for s in syms}


def test_py_signature_captured(tmp_root):
    _write(tmp_root, "app/fn.py", "def compute(x: int, y: int) -> int:\n    return x + y\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("app/fn.py")
    assert len(syms) == 1
    assert "compute" in syms[0]["signature"]


# ── TypeScript indexing ────────────────────────────────────────────────────

def test_ts_function_declaration(tmp_root):
    _write(tmp_root, "src/utils.ts", """
function greet(name: string): string {
    return `Hello ${name}`;
}

function add(a: number, b: number): number {
    return a + b;
}
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("src/utils.ts")
    names = {s["name"] for s in syms}
    assert "greet" in names
    assert "add" in names
    assert all(s["kind"] == "function" for s in syms)


def test_ts_arrow_function(tmp_root):
    _write(tmp_root, "src/helpers.ts", """
const double = (n: number) => n * 2;
const identity = <T>(x: T): T => x;
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("src/helpers.ts")
    names = {s["name"] for s in syms}
    assert "double" in names


def test_ts_class_and_method(tmp_root):
    _write(tmp_root, "src/service.ts", """
class UserService {
    getUser(id: string) {
        return id;
    }
    deleteUser(id: string) {
        return true;
    }
}
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("src/service.ts")
    names = {s["name"] for s in syms}
    assert "UserService" in names
    assert "getUser" in names
    assert "deleteUser" in names


def test_ts_interface(tmp_root):
    _write(tmp_root, "src/types.ts", """
interface IUser {
    id: string;
    name: string;
}
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("src/types.ts")
    names = {s["name"] for s in syms}
    assert "IUser" in names
    assert syms[0]["kind"] == "interface"


def test_tsx_component(tmp_root):
    _write(tmp_root, "src/Button.tsx", """
import React from 'react';

interface ButtonProps {
    label: string;
    onClick: () => void;
}

const Button = ({ label, onClick }: ButtonProps) => {
    return <button onClick={onClick}>{label}</button>;
};

export default Button;
""")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    syms = ix.get_symbols("src/Button.tsx")
    names = {s["name"] for s in syms}
    assert "Button" in names
    assert "ButtonProps" in names


# ── Mixed project ──────────────────────────────────────────────────────────

def test_index_all_mixed(tmp_root):
    _write(tmp_root, "api/main.py", "def start(): pass\ndef stop(): pass\n")
    _write(tmp_root, "web/app.ts", "function init(): void {}\nfunction teardown(): void {}\n")
    _write(tmp_root, "web/ui.tsx", "const App = () => <div/>;\n")

    ix = SymbolIndexer(tmp_root)
    files, symbols = ix.index_all()
    assert files == 3
    assert symbols >= 5


def test_skip_dirs(tmp_root):
    _write(tmp_root, "node_modules/lib/index.ts", "function secret() {}\n")
    _write(tmp_root, "src/real.ts", "function visible() {}\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    assert not ix.get_symbols("node_modules/lib/index.ts")
    assert ix.get_symbols("src/real.ts")


# ── Search ─────────────────────────────────────────────────────────────────

def test_keyword_search(tmp_root):
    _write(tmp_root, "app/auth.py", "def authenticate_user(token): pass\ndef logout(): pass\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    results = ix.search("authenticate")
    assert any("authenticate" in r["name"] for r in results)


def test_search_no_results(tmp_root):
    _write(tmp_root, "app/empty.py", "x = 1\n")
    ix = SymbolIndexer(tmp_root)
    ix.index_all()
    assert ix.search("nonexistent_xyz") == []
