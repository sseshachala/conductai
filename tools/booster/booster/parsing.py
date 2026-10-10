"""Tree-sitter symbol + call extraction for Python and TS/TSX."""
from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Node

PY_LANGUAGE = Language(tspython.language())
TS_LANGUAGE = Language(tsts.language_typescript())
TSX_LANGUAGE = Language(tsts.language_tsx())

_SKIP_DIRS = {"node_modules", ".venv", "__pycache__", ".git", ".booster", "worktrees", ".next", "dist", "build"}

_TS_EXTENSIONS = {".ts", ".tsx", ".js", ".jsx"}

_PY_KIND_MAP = {
    "function_definition": "function",
    "class_definition": "class",
}

_TS_KIND_MAP = {
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "interface_declaration": "interface",
}


def _extract_name(node: Node, source: bytes) -> str:
    for child in node.children:
        if child.type == "identifier":
            return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""


def _extract_ts_name(node: Node, source: bytes) -> str:
    if node.type == "method_definition":
        for child in node.children:
            if child.type == "property_identifier":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    else:
        for child in node.children:
            if child.type in ("identifier", "type_identifier"):
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return ""



def _extract_signature(node: Node, source: bytes) -> str:
    first_line_end = source.find(b"\n", node.start_byte)
    if first_line_end == -1:
        first_line_end = node.end_byte
    return source[node.start_byte:first_line_end].decode("utf-8", errors="replace").strip()[:300]


def _collect_ts_symbols(root_node: Node, source: bytes) -> list[tuple[str, str, int, int, str]]:
    """Walk TS/TSX AST, returning (name, kind, start_line, end_line, signature) tuples."""
    results: list[tuple[str, str, int, int, str]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type in _TS_KIND_MAP:
            name = _extract_ts_name(node, source)
            if name:
                sig = _extract_signature(node, source)
                results.append((name, _TS_KIND_MAP[node.type], node.start_point[0] + 1, node.end_point[0] + 1, sig))
        elif node.type == "lexical_declaration":
            # const foo = (...) => { ... }  — extract named arrow functions
            for declarator in node.children:
                if declarator.type != "variable_declarator":
                    continue
                has_arrow = any(c.type == "arrow_function" for c in declarator.children)
                if not has_arrow:
                    continue
                name = ""
                arrow_node: Node | None = None
                for child in declarator.children:
                    if child.type == "identifier" and not name:
                        name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                    if child.type == "arrow_function":
                        arrow_node = child
                if name and arrow_node:
                    sig = _extract_signature(declarator, source)
                    results.append((name, "function", arrow_node.start_point[0] + 1, arrow_node.end_point[0] + 1, sig))
                    continue  # don't recurse into arrow body for nested arrows
        stack.extend(node.children)
    return results


def _collect_py_calls(root_node: Node, source: bytes) -> list[tuple[str, int]]:
    """Walk Python AST for call sites, return (callee_name, line) tuples.

    ponytail: name-based; obj.foo() → 'foo', mod.cls.foo() → 'foo'.
    Cross-file resolution and method dispatch are resolved at query time.
    """
    calls: list[tuple[str, int]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "call" and node.children:
            fn = node.children[0]
            name = ""
            if fn.type == "identifier":
                name = source[fn.start_byte:fn.end_byte].decode("utf-8", errors="replace")
            elif fn.type == "attribute":
                for c in reversed(fn.children):
                    if c.type == "identifier":
                        name = source[c.start_byte:c.end_byte].decode("utf-8", errors="replace")
                        break
            if name:
                calls.append((name, node.start_point[0] + 1))
        stack.extend(node.children)
    return calls


def _collect_ts_calls(root_node: Node, source: bytes) -> list[tuple[str, int]]:
    """Walk TS/TSX AST for call sites, return (callee_name, line) tuples."""
    calls: list[tuple[str, int]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type == "call_expression" and node.children:
            fn = node.children[0]
            name = ""
            if fn.type == "identifier":
                name = source[fn.start_byte:fn.end_byte].decode("utf-8", errors="replace")
            elif fn.type == "member_expression":
                for c in reversed(fn.children):
                    if c.type == "property_identifier":
                        name = source[c.start_byte:c.end_byte].decode("utf-8", errors="replace")
                        break
            if name:
                calls.append((name, node.start_point[0] + 1))
        stack.extend(node.children)
    return calls


def _attribute_calls(
    calls: list[tuple[str, int]],
    symbols: list[tuple[int, int, int]],
) -> list[tuple[int, str, int]]:
    """Map each call to its enclosing symbol via line containment.

    symbols: list of (symbol_id, start_line, end_line).
    Returns: list of (source_symbol_id, callee_name, call_line).
    Skips calls not contained in any indexed symbol (module-level code).
    """
    # Sort symbols by range size ascending so the innermost match wins.
    ranked = sorted(symbols, key=lambda s: s[2] - s[1])
    out: list[tuple[int, str, int]] = []
    for callee, line in calls:
        for sid, s, e in ranked:
            if s <= line <= e:
                out.append((sid, callee, line))
                break
    return out


_TEST_FILE_PATTERNS = [
    "test_*.py", "*_test.py", "*.test.ts", "*.test.tsx", "*.test.js", "*.test.jsx",
    "*.spec.ts", "*.spec.tsx", "*.spec.js", "*.spec.jsx",
]


def _is_test_file(rel: str) -> bool:
    """Check whether a relative path looks like a test file."""
    name = Path(rel).name
    parts = Path(rel).parts
    if any(part in ("tests", "__tests__", "test") for part in parts):
        return True
    # quick pattern match against final filename
    if name.startswith("test_") and name.endswith(".py"):
        return True
    if name.endswith("_test.py"):
        return True
    for ext in (".ts", ".tsx", ".js", ".jsx"):
        if name.endswith(f".test{ext}") or name.endswith(f".spec{ext}"):
            return True
    return False



_COMMENT_PREFIXES = ("#", "//", "/*", "*")
_DOC_BODY_LINES = 10
_DOC_MAX_CHARS = 600


def _symbol_doc(lines: list[str], start_line: int, end_line: int) -> str:
    """Leading comment block + first body lines — the text search and embeddings see.

    Line-based so it works for every language: picks up Python docstrings (first
    body lines) and JSDoc / `#` comments directly above the definition.
    ponytail: first 10 body lines, not the whole body — keeps embeddings under the
    model's token window; long functions lose their tail.
    """
    above: list[str] = []
    i = start_line - 2  # 0-based index of the line above the definition
    while i >= 0 and lines[i].strip().startswith(_COMMENT_PREFIXES):
        above.append(lines[i].strip())
        i -= 1
    body = [ln.strip() for ln in lines[start_line:min(end_line, start_line + _DOC_BODY_LINES)]]
    return " ".join([*reversed(above), *body]).strip()[:_DOC_MAX_CHARS]


_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def split_identifier(text: str) -> str:
    """`_sendWithBackoff` / `send_with_backoff` → `send with backoff`."""
    return re.sub(r"[_\W]+", " ", _CAMEL.sub(" ", text)).strip().lower()


def _collect_py_symbols(root_node: Node, source: bytes) -> list[tuple[str, str, int, int, str]]:
    """Walk Python AST, returning (name, kind, start_line, end_line, signature) tuples."""
    results: list[tuple[str, str, int, int, str]] = []
    stack = [root_node]
    while stack:
        node = stack.pop()
        if node.type in _PY_KIND_MAP:
            name = _extract_name(node, source)
            if name:
                results.append((name, _PY_KIND_MAP[node.type], node.start_point[0] + 1,
                                node.end_point[0] + 1, _extract_signature(node, source)))
        stack.extend(node.children)
    return results
