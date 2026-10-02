import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conduct_cli.guard_commands import tool_lifecycle as lifecycle
from conduct_cli.tool_adapters import ADAPTERS


def test_windows_hook_command_preserves_quoted_executable_and_backslashes():
    command = '"C:\\Program Files\\Python\\python.exe" -m conduct_cli.hooks.session_usage codex'
    assert lifecycle._split_command(command, windows=True) == [
        'C:\\Program Files\\Python\\python.exe', '-m', 'conduct_cli.hooks.session_usage', 'codex']


def test_discovery_only_adapter_does_not_install_hooks(local, monkeypatch):
    from dataclasses import replace
    adapter = replace(ADAPTERS["codex"], id="example", hooks=None)
    monkeypatch.setitem(ADAPTERS, "example", adapter)
    adapter.root().mkdir()
    assert not lifecycle.configure_hooks("example", "python")
    assert not (adapter.root() / "hooks.json").exists()


@pytest.fixture
def local(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(lifecycle.shared, "GUARD_DIR", tmp_path / ".conduct")
    for variable in ("CODEX_HOME", "COPILOT_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(variable, raising=False)
    return {"api_url": "https://api.test.invalid", "mcp_url": "https://api.test.invalid/mcp",
            "workspace_id": "fixture-workspace", "agent_token": "cond_agt_fixture_only"}


@pytest.mark.parametrize("tool", list(ADAPTERS))
def test_setup_remove_is_idempotent_and_preserves_other_mcp(tool, local):
    adapter = ADAPTERS[tool]
    adapter.root().mkdir(parents=True)
    user = next(source for source in adapter.mcp_sources() if source.scope == "user")
    assert lifecycle.configure_mcp(tool, local)
    assert not lifecycle.configure_mcp(tool, local)
    from conduct_cli.tool_config import edit_document
    with edit_document(user.path) as document:
        document[user.key]["third-party"] = {"command": "never-run"}
    assert lifecycle.configure_mcp(tool, local, remove=True)
    assert not lifecycle.configure_mcp(tool, local, remove=True)
    with edit_document(user.path) as document:
        assert document[user.key] == {"third-party": {"command": "never-run"}}


@pytest.mark.parametrize("tool", list(ADAPTERS))
def test_hooks_roundtrip_preserves_user_hooks(tool, local):
    adapter = ADAPTERS[tool]
    adapter.root().mkdir(parents=True)
    assert lifecycle.configure_hooks(tool, "/python with spaces/python")
    assert not lifecycle.configure_hooks(tool, "/python with spaces/python")
    path = adapter.root() / ("settings.json" if tool == "claude-code" else
        "hooks/conduct-guard.json" if tool == "copilot-cli" else "hooks.json")
    config = json.loads(path.read_text())
    event = next(iter(config["hooks"]))
    own = {"type": "command", "command": "user-command"}
    user = own if tool in {"cursor", "windsurf", "copilot-cli"} else {"hooks": [own]}
    config["hooks"][event].append(user)
    path.write_text(json.dumps(config))
    assert lifecycle.configure_hooks(tool, "/other/python", remove=True)
    assert not lifecycle.configure_hooks(tool, "/other/python", remove=True)
    assert json.loads(path.read_text())["hooks"][event] == [user]


@pytest.mark.parametrize("tool", list(ADAPTERS))
def test_invalid_mcp_configuration_is_not_replaced(tool, local):
    adapter = ADAPTERS[tool]
    adapter.root().mkdir(parents=True)
    path = next(source.path for source in adapter.mcp_sources() if source.scope == "user")
    path.write_text("invalid [ text")
    with pytest.raises(ValueError):
        lifecycle.configure_mcp(tool, local)
    assert path.read_text() == "invalid [ text"


def test_custom_mcp_override_and_symlink_are_untouched(local, tmp_path):
    root = ADAPTERS["cursor"].root()
    root.mkdir()
    path = root / "mcp.json"
    original = {"mcpServers": {"conduct": {"command": "custom"}}}
    path.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="override"):
        lifecycle.configure_mcp("cursor", local)
    assert json.loads(path.read_text()) == original
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    try:
        path.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError, match="Symlinked"):
        lifecycle.configure_mcp("cursor", local)
    assert outside.read_text() == "{}"


def test_managed_mcp_refresh_switches_deployment_but_preserves_custom_entries(local):
    from conduct_cli.main import _write_mcp_config
    root = ADAPTERS["cursor"].root()
    root.mkdir()
    path = root / "mcp.json"
    assert lifecycle.configure_mcp("cursor", local)
    assert _write_mcp_config(path, api_url="https://different.test.invalid", token="cond_agt_new_fixture")
    entry = json.loads(path.read_text())["mcpServers"]["conduct"]
    assert entry["args"][2] == "https://different.test.invalid/mcp"
    assert entry["args"][-1] == "Authorization: Bearer cond_agt_new_fixture"


def test_disabled_state_survives_sync_and_stops_collectors(local, monkeypatch):
    root = ADAPTERS["codex"].root()
    root.mkdir()
    monkeypatch.setattr(lifecycle.shared, "_require_guard_config", lambda: local)
    lifecycle.run(SimpleNamespace(action="disable", tool="codex", project=None))
    assert lifecycle.disabled("codex")
    from conduct_cli.guard_commands import hooks
    hooks._install_codex_hook(Path.home() / ".conduct/hook.py")
    assert not (root / "hooks.json").exists()
    from conduct_cli.hooks.session_usage import collect
    assert not collect({}, "codex-desktop", ())
    lifecycle.run(SimpleNamespace(action="setup", tool="codex", project=None))
    assert not lifecycle.disabled("codex")
    assert (root / "hooks.json").exists()


def test_codex_gateway_roundtrip_restores_provider_and_preserves_comments(local, monkeypatch):
    local["gateway_url"] = "https://gateway.test.invalid/gateway/v1"
    root = ADAPTERS["codex"].root()
    root.mkdir()
    path = root / "config.toml"
    path.write_text('# keep this comment\nmodel_provider = "custom"\nmodel = "explicit-model"\n')
    from conduct_cli.guard_commands.gateway import _configure_codex_proxy
    assert _configure_codex_proxy(local["gateway_url"])
    lifecycle.configure_gateway("codex", local, remove=True)
    import tomlkit
    document = tomlkit.parse(path.read_text())
    assert document["model_provider"] == "custom"
    assert document["model"] == "explicit-model"
    assert "# keep this comment" in path.read_text()
    assert "conduct" not in document.get("model_providers", {})
