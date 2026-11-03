import json

import pytest

from conduct_cli import token_propagation
from conduct_cli.commands import shared
from conduct_cli.guard_commands import shared as guard_shared

OLD = "cond_agt_s1_" + "a" * 40
NEW = "cond_agt_s1_" + "b" * 40


@pytest.fixture
def clients(tmp_path, monkeypatch):
    mcp = tmp_path / ".mcp.json"
    mcp.write_text(json.dumps({"mcpServers": {"conduct": {"type": "http", "url": "https://x/mcp",
                                                          "headers": {"Authorization": f"Bearer {OLD}"}}}}))
    mcp.chmod(0o600)
    claude = tmp_path / ".claude.json"
    claude.write_text(json.dumps({"mcpServers": {"conduct": {"command": "npx",
                                                             "args": ["mcp-remote", "--header", f"Authorization: Bearer {OLD}"]}}}))
    unrelated = tmp_path / "other.json"
    unrelated.write_text('{"token": "keep"}')
    monkeypatch.setattr(token_propagation, "_candidate_paths", lambda: [mcp, claude, unrelated, tmp_path / "missing.json"])
    return mcp, claude, unrelated


def test_replaces_old_token_everywhere_it_appears(clients):
    mcp, claude, unrelated = clients
    updated = token_propagation.propagate_agent_token(OLD, NEW)
    assert set(updated) == {mcp, claude}
    for path in (mcp, claude):
        assert OLD not in path.read_text() and NEW in path.read_text()
    assert unrelated.read_text() == '{"token": "keep"}'
    assert mcp.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("old,new", [(None, NEW), (OLD, None), (OLD, OLD), ("short", NEW)])
def test_noop_inputs(clients, old, new):
    assert token_propagation.propagate_agent_token(old, new) == []


def test_symlinked_config_left_alone(tmp_path, monkeypatch):
    target = tmp_path / "real.json"
    target.write_text(OLD)
    link = tmp_path / "link.json"
    link.symlink_to(target)
    monkeypatch.setattr(token_propagation, "_candidate_paths", lambda: [link])
    assert token_propagation.propagate_agent_token(OLD, NEW) == []
    assert target.read_text() == OLD


def test_login_and_refresh_writes_propagate(clients, tmp_path, monkeypatch):
    mcp, _, _ = clients
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"agent_token": OLD}))
    monkeypatch.setattr(shared, "CONFIG_PATH", config)
    shared._atomic_write(config, {"agent_token": NEW})
    assert NEW in mcp.read_text()


def test_guard_config_save_propagates(clients, tmp_path, monkeypatch):
    mcp, _, _ = clients
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"agent_token": OLD}))
    monkeypatch.setattr(guard_shared, "CONFIG_PATH", config)
    monkeypatch.setattr(guard_shared, "CONDUCT_HOME", tmp_path)
    guard_shared._save_guard_config({"agent_token": NEW})
    assert NEW in mcp.read_text()


def test_other_files_written_by_atomic_write_do_not_propagate(clients, tmp_path):
    mcp, _, _ = clients
    shared._atomic_write(tmp_path / "policy.json", {"agent_token": NEW})
    assert OLD in mcp.read_text()
