"""Parent-directory .mcp.json files: token rotation reaches them and sync drops legacy keys."""
import json
import os
from pathlib import Path

import pytest

from conduct_cli import token_propagation
from conduct_cli.guard_commands import mcp as guard_mcp

OLD = "cond_agt_s1_" + "a" * 40
NEW = "cond_agt_s1_" + "b" * 40
# Captured at import, before the autouse conftest stub replaces it.
_REAL_CANDIDATES = token_propagation._candidate_paths


@pytest.fixture
def tree(tmp_path, monkeypatch):
    home = tmp_path / "home"
    repo = home / "projects" / "repo"
    repo.mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(repo)
    return home, repo


def _write(path, servers, mode=0o600):
    path.write_text(json.dumps({"mcpServers": servers}))
    path.chmod(mode)


def _legacy():
    return {"type": "http", "url": "https://api.conductai.ai/guard/mcp",
            "headers": {"Authorization": f"Bearer {OLD}"}}


def test_ancestors_run_from_cwd_up_to_home(tree):
    home, repo = tree
    assert token_propagation.ancestor_mcp_json() == [
        repo / ".mcp.json", repo.parent / ".mcp.json", home / ".mcp.json"]


def test_no_walk_outside_home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.chdir(tmp_path / "elsewhere")
    assert token_propagation.ancestor_mcp_json() == []


def test_rotation_updates_parent_mcp_json(tree, monkeypatch):
    home, repo = tree
    monkeypatch.setattr(token_propagation, "_candidate_paths", _REAL_CANDIDATES)
    parent = repo.parent / ".mcp.json"
    _write(parent, {"conduct": _legacy()})
    updated = token_propagation.propagate_agent_token(OLD, NEW)
    assert parent in updated
    assert NEW in parent.read_text() and OLD not in parent.read_text()


def test_sync_removes_legacy_keys_from_parents_only(tree):
    home, repo = tree
    parent = repo.parent / ".mcp.json"
    _write(parent, {"conduct-guard": _legacy(), "agent-booster": {"command": "booster"}}, mode=0o640)
    own = repo / ".mcp.json"
    _write(own, {"conduct-guard": _legacy()})
    cleaned = guard_mcp._clean_ancestor_mcp_json()
    assert cleaned == [parent]
    assert json.loads(parent.read_text())["mcpServers"] == {"agent-booster": {"command": "booster"}}
    assert os.stat(parent).st_mode & 0o777 == 0o640 or os.name == "nt"
    assert "conduct-guard" in json.loads(own.read_text())["mcpServers"]  # cwd handled by _write_mcp_file


def test_sync_leaves_unrelated_and_invalid_files(tree):
    home, repo = tree
    parent = repo.parent / ".mcp.json"
    _write(parent, {"other": {"command": "x"}})
    before = parent.read_text()
    (home / ".mcp.json").write_text("{not json")
    assert guard_mcp._clean_ancestor_mcp_json() == []
    assert parent.read_text() == before
