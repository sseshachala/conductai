"""Language table: extension → grammar, symbol node types, call node types.

Adding a language = one LANGS entry (+ a test). Python and TS keep their
hand-written collectors; everything else goes through the generic walkers.
"""
from __future__ import annotations

import importlib
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterator

from tree_sitter import Language, Node, Parser

from booster.parsing import (
    _SKIP_DIRS,
    _collect_py_calls,
    _collect_py_symbols,
    _collect_ts_calls,
    _collect_ts_symbols,
    _extract_signature,
)

Symbols = list[tuple[str, str, int, int, str]]  # (name, kind, start_line, end_line, signature)
Calls = list[tuple[str, int]]  # (callee_name, line)

# Generated/lock files dwarf real code and bury search results.
MAX_FILE_BYTES = 1_000_000

_IDENT = re.compile(r"[A-Za-z_~]\w*")


def _text(node: Node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _node_name(node: Node, source: bytes) -> str:
    """`name` field, else innermost `declarator` (C/C++), else `type` (Rust impl).

    Qualified names keep the last segment (`A::run` → `run`) so call edges, which
    store bare callee names, can resolve to them; the signature keeps the context.
    """
    n = node.child_by_field_name("name")
    if n is None:
        n = node.child_by_field_name("declarator")
        while n is not None and n.child_by_field_name("declarator") is not None:
            n = n.child_by_field_name("declarator")
    if n is None:
        n = node.child_by_field_name("type")
    if n is None:
        return ""
    raw = re.sub(r"<.*>", "", _text(n, source))  # Foo<T> → Foo
    toks = _IDENT.findall(re.split(r"::|\.|->", raw)[-1])
    return toks[0] if toks else ""


def _lines(node: Node) -> tuple[int, int]:
    """1-based (start, end). A node ending at column 0 stops before that line —
    YAML items swallow their trailing newline."""
    end_row, end_col = node.end_point
    return node.start_point[0] + 1, max(node.start_point[0] + 1, end_row + (end_col > 0))


def _walk(root: Node) -> Iterator[Node]:
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(node.children)


def generic_symbols(kinds: dict[str, str], need_body: frozenset[str] = frozenset()) -> Callable:
    def collect(root: Node, source: bytes) -> Symbols:
        out: Symbols = []
        for node in _walk(root):
            kind = kinds.get(node.type)
            if kind is None or (node.type in need_body and node.child_by_field_name("body") is None):
                continue
            name = _node_name(node, source)
            if name:
                out.append((name, kind, *_lines(node), _extract_signature(node, source)))
        return out
    return collect


def generic_calls(call_types: frozenset[str]) -> Callable:
    """Callee = last identifier of the `function` (or `name`) field.

    ponytail: textual — `s.helper(x)` → helper, `a::b::f()` → f; turbofish
    `f::<T>()` yields T. Upgrade path: per-grammar callee field walks.
    """
    def collect(root: Node, source: bytes) -> Calls:
        out: Calls = []
        for node in _walk(root):
            if node.type not in call_types:
                continue
            fn = node.child_by_field_name("function") or node.child_by_field_name("name")
            toks = _IDENT.findall(_text(fn, source)) if fn is not None else []
            if toks:
                out.append((toks[-1], node.start_point[0] + 1))
        return out
    return collect


def _yaml_symbols(root: Node, source: bytes) -> Symbols:
    """Top-level keys; second-level keys holding a mapping (`blocks.investigate`,
    `jobs.build`, `services.api`); list items with `id:`/`name:` near the top.

    ponytail: depth caps (2 / 3) keep deep k8s `env:` lists out of the index.
    """
    out: Symbols = []

    def is_mapping(value: Node | None) -> bool:
        return value is not None and any(c.type == "block_mapping" for c in value.children)

    def item_name(item: Node) -> str:
        mapping = next((n for n in _walk(item) if n.type == "block_mapping"), None)
        found = {}
        for pair in mapping.children if mapping is not None else []:
            k, v = pair.child_by_field_name("key"), pair.child_by_field_name("value")
            if pair.type == "block_mapping_pair" and k is not None and v is not None:
                found[_text(k, source).strip()] = _text(v, source).strip().strip("'\"")
        return found.get("id") or found.get("name") or ""

    def emit(name: str, kind: str, node: Node) -> None:
        out.append((name, kind, *_lines(node), _extract_signature(node, source)))

    def visit(node: Node, depth: int, parent: str) -> None:
        if node.type == "block_mapping_pair":
            key_node = node.child_by_field_name("key")
            key = _text(key_node, source).strip() if key_node is not None else ""
            if key and depth == 0:
                emit(key, "key", node)
            elif key and depth == 1 and is_mapping(node.child_by_field_name("value")):
                emit(f"{parent}.{key}", "block", node)
            for child in node.children:
                visit(child, depth + 1, key)
            return
        if node.type == "block_sequence_item" and depth <= 3:
            name = item_name(node)
            if name:
                emit(name, "item", node)
        for child in node.children:
            visit(child, depth, parent)

    visit(root, 0, "")
    return out


def _no_calls(root: Node, source: bytes) -> Calls:
    return []


@dataclass(frozen=True)
class Lang:
    name: str
    exts: tuple[str, ...]
    module: str  # tree_sitter_<x> package
    symbols: Callable[[Node, bytes], Symbols]
    calls: Callable[[Node, bytes], Calls]
    fn: str = "language"  # grammar function in the module
    # Read-gate: smart-read intercepts raw Reads only for gated languages. Config
    # files (YAML) get edited whole, so an outline instead of content would hurt.
    gate: bool = True
    _parser: list = field(default_factory=list, compare=False, repr=False)

    def parser(self) -> Parser:
        if not self._parser:
            mod = importlib.import_module(self.module)
            self._parser.append(Parser(Language(getattr(mod, self.fn)())))
        return self._parser[0]


_C_CALLS = generic_calls(frozenset({"call_expression"}))

LANGS: tuple[Lang, ...] = (
    Lang("python", (".py",), "tree_sitter_python", _collect_py_symbols, _collect_py_calls),
    Lang("typescript", (".ts", ".js"), "tree_sitter_typescript", _collect_ts_symbols, _collect_ts_calls,
         fn="language_typescript"),
    Lang("tsx", (".tsx", ".jsx"), "tree_sitter_typescript", _collect_ts_symbols, _collect_ts_calls,
         fn="language_tsx"),
    Lang("go", (".go",), "tree_sitter_go", generic_symbols({
        "function_declaration": "function", "method_declaration": "method", "type_spec": "type",
    }), _C_CALLS),
    Lang("rust", (".rs",), "tree_sitter_rust", generic_symbols({
        "function_item": "function", "struct_item": "struct", "enum_item": "enum",
        "trait_item": "trait", "impl_item": "impl", "mod_item": "module",
    }), _C_CALLS),
    Lang("java", (".java",), "tree_sitter_java", generic_symbols({
        "class_declaration": "class", "interface_declaration": "interface",
        "enum_declaration": "enum", "record_declaration": "class",
        "method_declaration": "method", "constructor_declaration": "method",
    }), generic_calls(frozenset({"method_invocation"}))),
    Lang("c", (".c",), "tree_sitter_c", generic_symbols(
        {"function_definition": "function", "struct_specifier": "struct", "enum_specifier": "enum"},
        need_body=frozenset({"struct_specifier", "enum_specifier"}),
    ), _C_CALLS),
    # .h → C++ grammar: it parses C headers fine and also handles C++ ones.
    Lang("cpp", (".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"), "tree_sitter_cpp", generic_symbols(
        {"function_definition": "function", "class_specifier": "class", "struct_specifier": "struct",
         "enum_specifier": "enum", "namespace_definition": "namespace"},
        need_body=frozenset({"class_specifier", "struct_specifier", "enum_specifier"}),
    ), _C_CALLS),
    Lang("bash", (".sh", ".bash"), "tree_sitter_bash", generic_symbols({"function_definition": "function"}),
         generic_calls(frozenset({"command"}))),
    Lang("yaml", (".yaml", ".yml"), "tree_sitter_yaml", _yaml_symbols, _no_calls, gate=False),
)

_BY_EXT = {ext: lang for lang in LANGS for ext in lang.exts}
SOURCE_EXTS = frozenset(_BY_EXT)


def lang_for(path: Path | str) -> Lang | None:
    return _BY_EXT.get(Path(path).suffix.lower())


def is_gated(path: Path | str) -> bool:
    lang = lang_for(path)
    return lang is not None and lang.gate


def iter_source_files(root: Path) -> Iterator[Path]:
    """Every indexable file under root; prunes skip dirs instead of walking into them."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for name in filenames:
            if Path(name).suffix.lower() in SOURCE_EXTS:
                p = Path(dirpath) / name
                try:
                    if p.stat().st_size <= MAX_FILE_BYTES:
                        yield p
                except OSError:
                    continue
