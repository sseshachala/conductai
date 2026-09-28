"""The static gate must recognize hook auth, not exempt hook routes."""
import ast
import importlib.util
from pathlib import Path


def test_hook_routes_require_recognized_auth_dependency():
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location("auth_coverage_gate", root / "scripts/check_auth_coverage.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    path = root / "app/modules/guard/routers/events.py"
    assert gate._scan_file(path) == []
    tree = ast.parse(path.read_text())
    names = {"ingest_event", "update_usage", "ingest_batch", "ingest_session_usage"}
    routes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert len(routes) == len(names)
    for route in routes:
        assert f"modules/guard/routers/events.py::{route.name}" not in gate.ALLOWLIST
        assert gate._has_auth(route)
        route.args.defaults = []
        route.args.kw_defaults = []
        assert not gate._has_auth(route)
