import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from conduct_cli.guard_commands import inventory


@pytest.fixture
def local(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.chdir(project)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    monkeypatch.setattr(inventory.shutil, "which", lambda _: None)
    return home, project


def test_device_id_is_stable_and_installations_are_distinct(local):
    assert inventory.device_id() == inventory.device_id()
    assert inventory.installation_id("codex") == inventory.installation_id("codex-desktop")
    assert inventory.installation_id("codex") != inventory.installation_id("claude-code")


def test_config_and_process_are_one_finding_without_arguments(local, monkeypatch):
    import psutil
    home, _ = local
    root = home / ".codex"
    root.mkdir()
    (root / "config.toml").write_text('model_provider = "conduct"\n[model_providers.conduct]\nbase_url = "https://gateway.conductai.ai/gateway/v1/openai/v1"\n')
    (root / "hooks.json").write_text(json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": f"python {home}/.conduct/hook.py"}]}]}}))
    def processes(fields):
        assert fields == ["name", "exe"]
        return [SimpleNamespace(info={"name": name, "exe": None}) for name in ("codex", "codex", "ShipIt", "Python", "Updater")]
    monkeypatch.setattr(psutil, "process_iter", processes)
    report = inventory.collect()
    assert len(report["agents"]) == 1
    agent = report["agents"][0]
    assert agent["detection"] == "running"
    assert agent["evidence"] == {"signals": ["running_executable", "tool_installation"], "hooks_configured": True,
                                 "gateway_configured": True, "mcp_configured": False}
    assert str(home) not in json.dumps(report)
    assert "cmdline" not in json.dumps(report)


def test_manifest_is_possible_not_running_and_config_only_skips_processes(local, monkeypatch):
    import psutil
    _, project = local
    (project / "package.json").write_text(json.dumps({"dependencies": {"@langchain/core": "1", "unrelated": "2"}}))
    (project / "pyproject.toml").write_text('[project]\ndependencies = ["langchain>=1"]\n')
    monkeypatch.setattr(psutil, "process_iter", lambda _: pytest.fail("config-only scanned processes"))
    result = inventory.collect(config_only=True)
    assert len(result["agents"]) == 1
    assert result["agents"][0]["detection"] == "possible_integration"
    assert result["agents"][0]["evidence"] == {"signals": ["dependency_manifest"]}


def test_malformed_config_is_partial_not_protected(local):
    home, _ = local
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("invalid")
    result = inventory.collect(config_only=True)
    assert result["status"] == "partial"
    assert result["errors"] == ["config_unreadable"]
    assert result["agents"][0]["evidence"] == {"signals": ["tool_installation"], "config_unreadable": True}


def test_copilot_custom_home_and_safe_evidence(local, monkeypatch):
    _, project = local
    root = project / "copilot-custom"
    (root / "hooks").mkdir(parents=True)
    monkeypatch.setenv("COPILOT_HOME", str(root))
    (root / "hooks" / "conduct-guard.json").write_text(json.dumps({"hooks": {"preToolUse": [{"exec": "python", "args": ["-m", "conduct_cli.hooks.copilot"]}]}}))
    result = inventory.collect(config_only=True)
    assert result["agents"][0]["framework"] == "copilot-cli"
    assert result["agents"][0]["evidence"]["hooks_configured"]
    assert "copilot-custom" not in json.dumps(result)


def test_upload_failure_is_explicit(local, monkeypatch, capsys):
    from conduct_cli.guard_commands import discovery
    monkeypatch.setattr(discovery._guard_shared, "_load_guard_config", lambda: {})
    monkeypatch.setattr(discovery._guard_shared, "_req", lambda *a, **kw: (_ for _ in ()).throw(SystemExit(1)))
    discovery.cmd_guard_discover(SimpleNamespace(config_only=True, report=None))
    assert "Upload failed; local findings only" in capsys.readouterr().out
