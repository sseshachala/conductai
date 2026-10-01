import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from conduct_cli.tool_adapters import ADAPTERS
from conduct_cli.tool_catalog import TOOLS
from conduct_cli.guard_commands import inventory
from conduct_cli.guard_commands.mcp_inventory import summarize_servers


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.chdir(tmp_path)
    for variable in ("CODEX_HOME", "COPILOT_HOME", "CLAUDE_CONFIG_DIR"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(inventory.shutil, "which", lambda _: None)
    return tmp_path


@pytest.mark.parametrize("tool", list(TOOLS))
def test_adapter_conformance_and_no_execution(tool, isolated, monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=AssertionError("Discovery executed a command")))
    adapter = ADAPTERS[tool]
    assert adapter.id == tool
    assert inventory.tool_root(tool) == adapter.root()
    source = adapter.mcp_sources()[0]
    source.path.parent.mkdir(parents=True, exist_ok=True)
    if source.path.suffix == ".toml":
        source.path.write_text('[mcp_servers.thirdparty]\ncommand = "do-not-run"\nargs = ["private-value"]\n')
    else:
        source.path.write_text(json.dumps({source.key: {"thirdparty": {
            "command": "do-not-run", "args": ["private-value"], "env": {"SECRET": "private-value"}}}}))
    finding = inventory.collect(config_only=True)["agents"][0]
    server = finding["evidence"]["mcp_servers"][0]
    assert server["name"] == "thirdparty"
    assert server["transport"] == "stdio"
    assert server["disabled"] is False
    assert len(server["id"]) == 64
    assert not finding["evidence"]["mcp_configured"]
    report = json.dumps(finding)
    for private in ("private-value", "do-not-run", str(isolated)):
        assert private not in report


def test_project_opt_in_scope_and_disabled_override(isolated):
    root = ADAPTERS["cursor"].root()
    root.mkdir()
    (root / "mcp.json").write_text(json.dumps({"mcpServers": {"conduct": {"url": "https://private.invalid/token"}}}))
    project = isolated / "project"
    (project / ".cursor").mkdir(parents=True)
    (project / ".cursor/mcp.json").write_text(json.dumps({"mcpServers": {"conduct": {"url": "https://other.invalid", "disabled": True}}}))
    default = inventory.collect(config_only=True)["agents"][0]["evidence"]
    assert len(default["mcp_servers"]) == 1
    assert default["mcp_configured"]
    selected = inventory.collect(config_only=True, project=project)["agents"][0]["evidence"]
    assert len(selected["mcp_servers"]) == 2
    assert len({s["id"] for s in selected["mcp_servers"]}) == 2
    assert not selected["mcp_configured"]
    assert "private.invalid" not in json.dumps(selected)


def test_project_symlink_escape_rejected(isolated):
    project = isolated / "project"
    (project / ".cursor").mkdir(parents=True)
    outside = isolated / "outside.json"
    outside.write_text("{}")
    try:
        (project / ".cursor/mcp.json").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        ADAPTERS["cursor"].mcp_sources(project)


def test_invalid_and_oversized_server_maps_are_not_success(isolated):
    adapter = ADAPTERS["cursor"]
    adapter.root().mkdir()
    for data in (["invalid"], {str(i): {} for i in range(101)}):
        (adapter.root() / "mcp.json").write_text(json.dumps({"mcpServers": data}))
        report = inventory.collect(config_only=True)
        assert report["status"] == "partial"
        assert report["agents"][0]["evidence"]["config_unreadable"]


def test_detection_does_not_infer_editor_gateway_from_shared_env(isolated, monkeypatch):
    from conduct_cli.guard_commands.discovery import _detect_ai_tools
    ADAPTERS["cursor"].root().mkdir()
    ADAPTERS["windsurf"].root().mkdir(parents=True)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.conductai.ai/gateway/v1/anthropic")
    findings = _detect_ai_tools()
    assert {f["name"] for f in findings} == {"cursor", "windsurf"}
    assert all(not f["proxy_routed"] for f in findings)


def test_sync_targets_match_discovery_and_preserve_unowned_entries(isolated, monkeypatch):
    from types import SimpleNamespace
    from conduct_cli.guard_commands import mcp
    for tool in ("claude-code", "cursor", "windsurf"):
        ADAPTERS[tool].root().mkdir(parents=True)
    cursor = ADAPTERS["cursor"].root() / "mcp.json"
    override = {"mcpServers": {"conduct": {"command": "custom-command"}, "thirdparty": {"command": "another"}}}
    cursor.write_text(json.dumps(override))
    monkeypatch.setattr(mcp, "_deployment", lambda _: SimpleNamespace(mcp="https://test.invalid/mcp", gateway=None))
    monkeypatch.setattr(mcp, "_patch_copilot_mcp", lambda *a: None)
    monkeypatch.setattr(mcp._guard_instructions, "_patch_cursor_global_rules", lambda: None)
    monkeypatch.setattr(mcp._guard_instructions, "_patch_tool_instruction_files", lambda *a, **kw: None)
    mcp._register_mcp("workspace", "synthetic-test-only", "https://test.invalid")
    assert json.loads(cursor.read_text()) == override
    for tool in ("claude-code", "windsurf"):
        source = next(s for s in ADAPTERS[tool].mcp_sources() if s.scope == "user")
        assert "conduct" in json.loads(source.path.read_text())[source.key]
    assert not (isolated / ".windsurf").exists()


def test_codex_mcp_uses_custom_home_without_overwriting_invalid_config(isolated, monkeypatch):
    from conduct_cli.main import _write_codex_mcp_config
    root = isolated / "custom-codex"
    root.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(root))
    config = root / "config.toml"
    config.write_text("not valid [ toml")
    assert not _write_codex_mcp_config("https://test.invalid", "synthetic-test-only")
    assert config.read_text() == "not valid [ toml"
