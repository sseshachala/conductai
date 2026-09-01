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
        "agent_token": "cond_agt_testkey",
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
    """conduct switch 'Marketing' updates unified ~/.conduct/config.json and re-syncs guard policy."""
    from conduct_cli import main as m
    from conduct_cli import guard as g

    cfg_path = tmp_path / "conduct" / "config.json"
    cfg_path.parent.mkdir(parents=True)

    cfg_path.write_text(json.dumps({
        "server":    "https://api.conductai.ai",
        "agent_token": "cond_agt_testkey",
        "workspace": "ef0a7e36-0000-0000-0000-000000000001",
    }))

    args = _make_args(workspace="Marketing")

    fake_policy = {"version": "2", "rules": [{"rule_id": "r1", "action": "audit"}]}

    def _api_req(method, url, hdrs, body=None, timeout=30):
        if method == "GET" and url.endswith("/projects"):
            return _fake_workspaces()
        if method == "POST" and url.endswith("/auth/switch-workspace"):
            return {"agent_token": "cond_agt_remint_new", "expires_in": 28800}
        raise AssertionError(f"unexpected call {method} {url}")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", side_effect=_api_req),
        patch.object(g, "_req", return_value=fake_policy),
        patch.object(g, "_save_policy") as mock_save_policy,
    ):
        m.cmd_switch(args)

    out = capsys.readouterr().out
    assert "Marketing" in out
    assert "ab1b2c3d" in out   # first 8 chars of the new workspace id

    updated_cfg = json.loads(cfg_path.read_text())
    assert updated_cfg["workspace"] == "ab1b2c3d-0000-0000-0000-000000000002"
    assert updated_cfg["workspace_id"] == "ab1b2c3d-0000-0000-0000-000000000002"

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
        "agent_token": "cond_agt_testkey",
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
        "agent_token": "cond_agt_testkey",
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
        "server":      "https://api.conductai.ai",
        "agent_token": "cond_agt_88a4longkeyxxx",
        "workspace":   "ef0a7e36-0000-0000-0000-000000000001",
        "user_email":  "sudhi@b2bsphere.com",
    }))

    # Guard uses ~/.conduct/ now — policy.json here, hook.py absent
    guard_dir = tmp_path / ".conduct"
    guard_dir.mkdir(exist_ok=True)
    (guard_dir / "policy.json").write_text(json.dumps({
        "version": "1",
        "rules":   [{"rule_id": "r1"}, {"rule_id": "r2"}, {"rule_id": "r3"}],
    }))

    args = _make_args()

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
    ):
        m.cmd_whoami(args)

    out = capsys.readouterr().out
    assert "https://api.conductai.ai" in out
    assert "cond_agt_88a" in out   # first 12 chars of the agent_token
    assert "sudhi@b2bsphere.com" in out
    assert "3 rules" in out
    assert "Booster" in out


# ---------------------------------------------------------------------------
# Regression: cmd_switch must accept `api_url` when `server` is absent.
# `conduct login` writes `api_url`; older cmd_switch only read `server`
# and falsely reported "Not logged in".
# ---------------------------------------------------------------------------

def test_switch_accepts_api_url_key(tmp_path, capsys):
    """conduct switch works when config was written by `conduct login` (api_url only)."""
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({
        "api_url":     "https://api.conductai.ai",
        "agent_token": "cond_agt_testkey",
        "workspace":   "ef0a7e36-0000-0000-0000-000000000001",
    }))

    args = _make_args(workspace=None)

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
    ):
        m.cmd_switch(args)

    out = capsys.readouterr().out
    assert "Not logged in" not in out
    assert "Engineering" in out


# ---------------------------------------------------------------------------
# Regression: `conduct login` prints workspace name (not just UUID) and a
# switch-hint when the account has more than one workspace. Cross-surface
# workspace drift (web-UI-switched, CLI still on old) was invisible before.
# ---------------------------------------------------------------------------

def test_login_shows_name_and_nudges_when_multiple_workspaces(tmp_path, capsys):
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({}))
    args = _make_args(server=None, token=None)

    fake_result = {
        "agent_token": "cond_agt_testkey",
        "workspace_id": "ef0a7e36-0000-0000-0000-000000000001",
    }

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m, "_web_login_flow", return_value=fake_result),
        patch.object(m.api, "req", return_value=_fake_workspaces()),
        patch("conduct_cli.guard.cmd_guard_sync", return_value=None),
    ):
        m.cmd_login(args)

    out = capsys.readouterr().out
    # Current workspace displayed by name (not just UUID)
    assert "Engineering" in out
    # Nudge appears because account has >1 workspace
    assert "conduct switch" in out
    # Other workspace names surfaced in the preview
    assert "Marketing" in out or "Eng Backup" in out


def test_login_omits_nudge_when_single_workspace(tmp_path, capsys):
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({}))
    args = _make_args(server=None, token=None)

    fake_result = {
        "agent_token": "cond_agt_testkey",
        "workspace_id": "ef0a7e36-0000-0000-0000-000000000001",
    }
    single_ws = [{"id": "ef0a7e36-0000-0000-0000-000000000001", "name": "Only", "owner_id": "u1", "workflow_count": 0}]

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m, "_web_login_flow", return_value=fake_result),
        patch.object(m.api, "req", return_value=single_ws),
        patch("conduct_cli.guard.cmd_guard_sync", return_value=None),
    ):
        m.cmd_login(args)

    out = capsys.readouterr().out
    assert "Only" in out
    assert "conduct switch" not in out


# ---------------------------------------------------------------------------
# Fix A regression: cmd_switch must re-mint the agent token by calling
# POST /auth/switch-workspace so server-side attribution follows the local
# workspace flip. Without this, POSTs after switch keep hitting the
# original workspace.
# ---------------------------------------------------------------------------

def test_switch_remints_agent_token_via_endpoint(tmp_path, monkeypatch, capsys):
    from conduct_cli import main as m
    from conduct_cli import guard as g

    cfg_path = tmp_path / "conduct" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({
        "api_url":     "https://api.conductai.ai",
        "agent_token": "cond_agt_ORIGINAL_engineering",
        "workspace":   "ef0a7e36-0000-0000-0000-000000000001",
    }))

    args = _make_args(workspace="Marketing")
    remint_response = {
        "agent_token":   "cond_agt_NEW_marketing_scoped",
        "refresh_token": "cond_ref_new_refresh",
        "expires_in":    28800,
        "workspace_id":  "ab1b2c3d-0000-0000-0000-000000000002",
        "user_id":       "user_test",
    }

    def _api_req(method, url, hdrs, body=None, timeout=30):
        if method == "GET" and url.endswith("/projects"):
            return _fake_workspaces()
        if method == "POST" and url.endswith("/auth/switch-workspace"):
            assert body == {"workspace_id": "ab1b2c3d-0000-0000-0000-000000000002"}
            return remint_response
        raise AssertionError(f"unexpected call {method} {url}")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", side_effect=_api_req),
        patch.object(g, "_req", return_value={"version": "1", "rules": []}),
        patch.object(g, "_save_policy"),
    ):
        m.cmd_switch(args)

    updated_cfg = json.loads(cfg_path.read_text())
    assert updated_cfg["agent_token"]  == "cond_agt_NEW_marketing_scoped"
    assert updated_cfg["refresh_token"] == "cond_ref_new_refresh"
    assert updated_cfg["workspace_id"] == "ab1b2c3d-0000-0000-0000-000000000002"
    assert "token_expires_at" in updated_cfg


def test_switch_hard_exits_when_remint_fails(tmp_path, monkeypatch, capsys):
    """If the switch-workspace endpoint fails, hard-exit — a stale token pointing at the
    wrong workspace is worse than making the user re-login."""
    from conduct_cli import main as m
    from conduct_cli import guard as g

    cfg_path = tmp_path / "conduct" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({
        "api_url":     "https://api.conductai.ai",
        "agent_token": "cond_agt_ORIGINAL",
        "workspace":   "ef0a7e36-0000-0000-0000-000000000001",
    }))
    args = _make_args(workspace="Marketing")

    def _api_req(method, url, hdrs, body=None, timeout=30):
        if method == "GET" and url.endswith("/projects"):
            return _fake_workspaces()
        # Endpoint failure — mimic api.req's SystemExit on HTTP error
        raise SystemExit(1)

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", side_effect=_api_req),
        patch.object(g, "_req", return_value={"version": "1", "rules": []}),
        patch.object(g, "_save_policy"),
    ):
        with pytest.raises(SystemExit) as exc:
            m.cmd_switch(args)
        assert exc.value.code == 1

    out = capsys.readouterr().out
    assert "token re-mint failed" in out
    # Config untouched — no partial write when re-mint fails
    unchanged = json.loads(cfg_path.read_text())
    assert unchanged["agent_token"] == "cond_agt_ORIGINAL"
    assert unchanged["workspace"] == "ef0a7e36-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# 0.9.9 — cmd_switch must fire _report_tool_coverage so the new workspace's
# "developer connected" widget populates immediately (not just after next login)
# ---------------------------------------------------------------------------

def test_switch_fires_tool_coverage(tmp_path, monkeypatch, capsys):
    from conduct_cli import main as m
    from conduct_cli import guard as g

    cfg_path = tmp_path / "conduct" / "config.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({
        "api_url":     "https://api.conductai.ai",
        "agent_token": "cond_agt_test",
        "workspace":   "ef0a7e36-0000-0000-0000-000000000001",
    }))
    args = _make_args(workspace="Marketing")

    def _api_req(method, url, hdrs, body=None, timeout=30):
        if method == "GET" and url.endswith("/projects"):
            return _fake_workspaces()
        if method == "POST" and url.endswith("/auth/switch-workspace"):
            return {"agent_token": "cond_agt_new", "expires_in": 28800, "workspace_id": body["workspace_id"], "user_id": "u1"}
        raise AssertionError(f"unexpected call {method} {url}")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch("pathlib.Path.home", return_value=tmp_path),
        patch.object(m.api, "req", side_effect=_api_req),
        patch.object(g, "cmd_guard_sync") as sync,
    ):
        m.cmd_switch(args)

    # 0.9.10: cmd_switch delegates surface propagation (env, MCP, hooks,
    # coverage) to cmd_guard_sync — one hop, all clients follow.
    sync.assert_called_once()


# ---------------------------------------------------------------------------
# 0.9.9 — cmd_login must preserve the prior workspace_id if it differs from
# the server-returned default. Otherwise every re-login blows away the user's
# last `conduct switch`.
# ---------------------------------------------------------------------------

def test_login_preserves_prior_workspace(tmp_path, capsys):
    from conduct_cli import main as m

    cfg_path = tmp_path / "config.json"
    # Prior state: user was on Marketing (via a previous switch)
    cfg_path.write_text(json.dumps({
        "api_url":     "https://api.conductai.ai",
        "agent_token": "cond_agt_old",
        "workspace":   "ab1b2c3d-0000-0000-0000-000000000002",
        "workspace_id": "ab1b2c3d-0000-0000-0000-000000000002",
    }))
    args = _make_args(server=None, token=None)

    # Login returns Engineering (server default) — but prior was Marketing
    fake_login_result = {
        "agent_token": "cond_agt_from_login_engineering",
        "workspace_id": "ef0a7e36-0000-0000-0000-000000000001",
    }
    remint_response = {
        "agent_token": "cond_agt_reminted_for_marketing",
        "refresh_token": "cond_ref_reminted",
        "expires_in": 28800,
        "workspace_id": "ab1b2c3d-0000-0000-0000-000000000002",
        "user_id": "u1",
    }

    def _api_req(method, url, hdrs, body=None, timeout=30):
        if method == "POST" and url.endswith("/auth/switch-workspace"):
            # Should be called with prior_ws (Marketing UUID)
            assert body == {"workspace_id": "ab1b2c3d-0000-0000-0000-000000000002"}
            return remint_response
        if method == "GET" and url.endswith("/projects"):
            return _fake_workspaces()
        raise AssertionError(f"unexpected call {method} {url}")

    with (
        patch.object(m, "CONFIG_PATH", cfg_path),
        patch.object(m, "_web_login_flow", return_value=fake_login_result),
        patch.object(m.api, "req", side_effect=_api_req),
        patch("conduct_cli.guard.cmd_guard_sync", return_value=None),
    ):
        m.cmd_login(args)

    updated_cfg = json.loads(cfg_path.read_text())
    assert updated_cfg["workspace_id"] == "ab1b2c3d-0000-0000-0000-000000000002"
    assert updated_cfg["agent_token"] == "cond_agt_reminted_for_marketing"
    assert updated_cfg["refresh_token"] == "cond_ref_reminted"
