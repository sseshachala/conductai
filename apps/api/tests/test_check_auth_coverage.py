"""Tests for scripts/check_auth_coverage.py."""
import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_auth_coverage.py"
_spec = importlib.util.spec_from_file_location("check_auth_coverage", SCRIPT)
cac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cac)


def _make_root(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, src in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src)
    return tmp_path


ASYNC_NO_AUTH = '''
from fastapi import APIRouter
router = APIRouter()

@router.get("/open")
async def open_route():
    return {}
'''

ASYNC_WITH_AUTH = '''
from typing import Annotated
from fastapi import APIRouter, Depends
router = APIRouter()

@router.get("/a")
async def a(_: str = Depends(require_permission("platform.workflows.view"))):
    return {}

@router.get("/b")
async def b(ws: Annotated[str, Depends(get_workspace_id)]):
    return {}
'''


def test_async_route_without_auth_is_flagged(tmp_path):
    root = _make_root(tmp_path, {"app/routers/fixture.py": ASYNC_NO_AUTH})
    found = cac._scan_file(root / "app/routers/fixture.py", root, set())
    assert found == ["routers/fixture.py::open_route"]


def test_async_route_with_auth_passes(tmp_path):
    root = _make_root(tmp_path, {"app/routers/fixture.py": ASYNC_WITH_AUTH})
    assert cac._scan_file(root / "app/routers/fixture.py", root, set()) == []


def test_websocket_and_app_decorators_are_flagged(tmp_path):
    src = '''
@app.websocket("/ws")
async def ws(websocket):
    pass

@app.get("/x")
def x():
    pass
'''
    root = _make_root(tmp_path, {"app/main.py": src})
    found = cac._scan_file(root / "app/main.py", root, set())
    assert sorted(found) == ["main.py::ws", "main.py::x"]


def test_entrypoint_files_are_scanned(tmp_path):
    root = _make_root(
        tmp_path,
        {"app/routers/ok.py": "", "app/modules/__init__.py": "", "app/main.py": "", "app/mcp/http.py": ""},
    )
    names = {str(p.relative_to(root)) for p in cac._scan_files(root)}
    assert {"app/main.py", "app/mcp/http.py"} <= names


def test_stale_allowlist_entries_detected(tmp_path):
    root = _make_root(tmp_path, {"app/routers/fixture.py": ASYNC_NO_AUTH, "app/modules/x.py": ""})
    allow = {"routers/fixture.py::open_route", "routers/gone.py::health", "routers/fixture.py::renamed"}
    assert cac.find_stale_allowlist(root, allow) == ["routers/fixture.py::renamed", "routers/gone.py::health"]


def test_repo_has_no_unprotected_or_stale_routes():
    violations = [v for f in cac._scan_files(cac.ROOT) for v in cac._scan_file(f)]
    assert violations == []
    assert cac.find_stale_allowlist() == []
