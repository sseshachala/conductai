"""Tests for `conduct switch` and `conduct whoami` commands."""

import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_args(**kwargs):
    ns = types.SimpleNamespace(**kwargs)
    return ns


def _fake_workspaces():
    return [
        {"id": "ef0a7e36-0000-0000-0000-000000000001", "name": "Engineering",    "owner_id": "u1", "workflow_count": 3},
        {"id": "ab1b2c3d-0000-0000-0000-000000000002", "name": "Marketing",      "owner_id": "u1", "workflow_count": 1},
        {"id": "deadbeef-0000-0000-0000-000000000003", "name": "Eng Backup",     "owner_id": "u1", "workflow_count": 0},
    ]


# ---------------------------------------------------------------------------
# cmd_switch — list mode (no arg)
# ---------------------------------------------------------------------------

def test_switch_list_prints_workspaces(tmp_path, capsys):
    """conduct switch with no arg exits 0 and prints workspace list."""
    from conduct_cli import main as m

    config = {
        "server":    "https://api.conductai.ai",
        "api_key":   "cond_live_testkey",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(config))

    args = _make_args(workspace=None)

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
    ):
        m.cmd_switch(args)

    out = capsys.readouterr().out
    assert "Engineering" in out
    assert "Marketing"   in out
    assert "*" in out          # current workspace marked


# ---------------------------------------------------------------------------
# cmd_switch — exact match updates both config files
# ---------------------------------------------------------------------------

def test_switch_exact_name_updates_configs(tmp_path, capsys):
    """conduct switch 'Marketing' updates ~/.conduct/config.json and guard config."""
    from conduct_cli import main as m
    from conduct_cli import guard as g

    cfg_path        = tmp_path / "conduct" / "config.json"
    # Guard config lives at <home>/.conductguard/config.json; home is patched to tmp_path
    guard_cfg_path  = tmp_path / ".conductguard" / "config.json"

    cfg_path.parent.mkdir(parents=True)
    guard_cfg_path.parent.mkdir(parents=True)

    cfg_path.write_text(json.dumps({
        "server":    "https://api.conductai.ai",
        "api_key":   "cond_live_testkey",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }))
    guard_cfg_path.write_text(json.dumps({
        "workspace_id": "ef0a7e36-0000-0000-0000-000000000001",
        "user_email":   "dev@example.com",
    }))

    args = _make_args(workspace="Marketing")

    fake_policy = {"version": "2", "rules": [{"rule_id": "r1", "action": "audit"}]}

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
        patch.object(g, "_req", return_value=fake_policy),
        patch.object(g, "_save_policy") as mock_save_policy,
    ):
        m.cmd_switch(args)

    out = capsys.readouterr().out
    assert "Marketing" in out
    assert "ab1b2c3d" in out   # first 8 chars of the new workspace id

    updated_cfg = json.loads(cfg_path.read_text())
    assert updated_cfg["workspace"] == "ab1b2c3d-0000-0000-0000-000000000002"

    updated_guard = json.loads(guard_cfg_path.read_text())
    assert updated_guard["workspace_id"] == "ab1b2c3d-0000-0000-0000-000000000002"

    mock_save_policy.assert_called_once_with(fake_policy)


# ---------------------------------------------------------------------------
# cmd_switch — ambiguous partial match
# ---------------------------------------------------------------------------

def test_switch_ambiguous_exits_1(tmp_path, capsys):
    """Partial match that hits multiple workspaces prints error and exits 1."""
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "server":    "https://api.conductai.ai",
        "api_key":   "cond_live_testkey",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }))

    # "Eng" matches both "Engineering" and "Eng Backup"
    args = _make_args(workspace="Eng")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
        pytest.raises(SystemExit) as exc,
    ):
        m.cmd_switch(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Ambiguous" in out or "ambiguous" in out.lower() or "more specific" in out


# ---------------------------------------------------------------------------
# cmd_switch — no match exits 1
# ---------------------------------------------------------------------------

def test_switch_no_match_exits_1(tmp_path, capsys):
    """conduct switch 'Nonexistent' exits 1 and lists available workspaces."""
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "server":    "https://api.conductai.ai",
        "api_key":   "cond_live_testkey",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }))

    args = _make_args(workspace="Nonexistent")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
        pytest.raises(SystemExit) as exc,
    ):
        m.cmd_switch(args)

    assert exc.value.code == 1
    out = capsys.readouterr().out
    assert "Engineering" in out   # shows available list


# ---------------------------------------------------------------------------
# cmd_whoami — basic output
# ---------------------------------------------------------------------------

def test_whoami_prints_all_sections(tmp_path, capsys):
    """conduct whoami prints workspace, server, api_key, Guard, and Booster lines."""
    from conduct_cli import main as m

    cfg_path = tmp_path / "conduct" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({
        "server":    "https://api.conductai.ai",
        "api_key":   "cond_live_88a4longkeyxxx",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }))

    guard_dir = tmp_path / ".conductguard"
    guard_dir.mkdir()
    (guard_dir / "config.json").write_text(json.dumps({
        "workspace_id": "ef0a7e36-0000-0000-0000-000000000001",
        "user_email":   "sudhi@b2bsphere.com",
    }))
    (guard_dir / "policy.json").write_text(json.dumps({
        "version": "1",
        "rules":   [{"rule_id": "r1"}, {"rule_id": "r2"}, {"rule_id": "r3"}],
    }))
    # No hook.py — hook_status should say "hook missing"

    args = _make_args()

    def fake_home():
        return tmp_path

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
    ):
        m.cmd_whoami(args)

    out = capsys.readouterr().out
    assert "https://api.conductai.ai" in out
    assert "cond_live_88" in out   # first 12 chars of the api_key
    assert "sudhi@b2bsphere.com" in out
    assert "3 rules" in out
    assert "Booster" in out
