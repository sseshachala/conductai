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


@pytest.mark.parametrize("options,expected", [({}, True), ({"verify_gateway": True}, True), ({"verify_gateway": False}, False)])
def test_discovery_gateway_check_and_upload_failure(local, monkeypatch, capsys, options, expected):
    from conduct_cli.guard_commands import discovery
    from unittest.mock import Mock
    probe = Mock()
    monkeypatch.setattr(inventory, "verify_gateway", probe)
    monkeypatch.setattr(discovery._guard_shared, "_load_guard_config", lambda: {})
    monkeypatch.setattr(discovery._guard_shared, "_req", lambda *a, **kw: (_ for _ in ()).throw(SystemExit(1)))
    discovery.cmd_guard_discover(SimpleNamespace(config_only=True, report=None, **options))
    assert probe.call_count == int(expected)
    assert "Upload failed; local findings only" in capsys.readouterr().out


def test_claude_inherited_gateway_url_and_settings_precedence(local, monkeypatch):
    home, _ = local
    root = home / ".claude"
    root.mkdir()
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://gateway.conductai.ai/gateway/v1/anthropic")
    assert inventory.collect(config_only=True)["agents"][0]["evidence"]["gateway_configured"]
    (root / "settings.json").write_text(json.dumps({"env": {"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}}))
    assert not inventory.collect(config_only=True)["agents"][0]["evidence"]["gateway_configured"]


@pytest.mark.parametrize("status,body,expected", [
    (200, b'{"data":[]}', "connection_verified"),
    (200, b'<html>not an API</html>', "unavailable"),
    (302, b'', "unavailable"), (401, b'', "authentication_failed"),
    (403, b'', "authentication_failed"), (500, b'', "unavailable"),
])
def test_gateway_probe_is_bounded_authenticated_and_no_redirects(monkeypatch, status, body, expected):
    from unittest.mock import Mock
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(status=status, read=lambda limit: body)
    factory = Mock(return_value=connection)
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", factory)
    report = {"agents": [{"framework": "claude-code", "evidence": {"gateway_configured": True}}]}
    inventory.verify_gateway(report, "cond_agt_test_only")
    factory.assert_called_once_with("gateway.conductai.ai", timeout=8)
    connection.request.assert_called_once_with("GET", "/gateway/v1/anthropic/v1/models", headers={"Authorization": "Bearer cond_agt_test_only"})
    connection.close.assert_called_once()
    assert report["agents"][0]["evidence"]["gateway_connection_status"] == expected


def test_gateway_probe_never_sends_provider_credentials(monkeypatch):
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", lambda *a, **k: pytest.fail("Unexpected network request"))
    report = {"agents": [{"framework": "codex", "evidence": {"gateway_configured": True}}]}
    inventory.verify_gateway(report, "provider-test-key")
    assert report["agents"][0]["evidence"]["gateway_connection_status"] == "authentication_failed"


@pytest.mark.parametrize("tool,provider,key", [
    ("claude-code", "anthropic", "data"),
    ("codex", "openai", "models"),
    ("copilot-cli", "openai", "models"),
])
@pytest.mark.parametrize("status", [200, 302, 401, 403, 500])
def test_all_clients_verify_the_selected_deployment(monkeypatch, tool, provider, key, status):
    from unittest.mock import Mock
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(
        status=status, read=lambda limit: json.dumps({key: []}).encode())
    factory = Mock(return_value=connection)
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", factory)
    report = {"agents": [{"framework": tool, "evidence": {"gateway_configured": True}}]}
    config = {"api_url": "https://api.example", "gateway_url": "https://private.example/gateway/v1"}
    inventory.verify_gateway(report, "cond_agt_test_only", config)
    factory.assert_called_once_with("private.example", timeout=8)
    connection.request.assert_called_once_with("GET", f"/gateway/v1/{provider}/v1/models",
                                              headers={"Authorization": "Bearer cond_agt_test_only"})
    expected = "connection_verified" if status == 200 else "authentication_failed" if status in (401, 403) else "unavailable"
    assert report["agents"][0]["evidence"]["gateway_connection_status"] == expected
    assert "cond_agt_" not in json.dumps(report)
    connection.close.assert_called_once()


def test_codex_and_copilot_share_one_probe_and_unknown_tools_are_not_verified(monkeypatch):
    from unittest.mock import Mock
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(status=200, read=lambda limit: b'{"models":[]}')
    factory = Mock(return_value=connection)
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", factory)
    report = {"agents": [{"framework": tool, "evidence": {"gateway_configured": configured}}
                         for tool, configured in [("codex", True), ("copilot-cli", True), ("claude-code", False), ("cursor", True)]]}
    inventory.verify_gateway(report, "cond_agt_test_only")
    factory.assert_called_once()
    for item in report["agents"][:2]:
        assert item["evidence"]["gateway_connection_status"] == "connection_verified"
    for item in report["agents"][2:]:
        assert "gateway_connection_status" not in item["evidence"]


@pytest.mark.parametrize("body", [b'{"data":[]}', b'{"models":null}', b'{"models":{}}', b'{}', b'not-json'])
def test_openai_probe_rejects_wrong_catalog_shape(monkeypatch, body):
    from unittest.mock import Mock
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(status=200, read=lambda limit: body)
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", lambda *a, **kw: connection)
    report = {"agents": [{"framework": "copilot-cli", "evidence": {"gateway_configured": True}}]}
    inventory.verify_gateway(report, "cond_agt_test_only")
    assert report["agents"][0]["evidence"]["gateway_connection_status"] == "unavailable"


def test_local_discovery_prints_probe_and_mcp_results_when_upload_fails(local, monkeypatch, capsys):
    from conduct_cli.guard_commands import discovery
    report = {"status": "complete", "agents": [{"framework": "copilot-cli", "detection": "installed",
              "evidence": {"gateway_configured": True, "gateway_connection_status": "connection_verified",
                           "hooks_configured": True, "mcp_configured": True}}]}
    monkeypatch.setattr(inventory, "collect", lambda *a: report)
    monkeypatch.setattr(inventory, "verify_gateway", lambda *a: None)
    monkeypatch.setattr(discovery._guard_shared, "_load_guard_config", lambda: {})
    monkeypatch.setattr(discovery._guard_shared, "_req", lambda *a, **kw: (_ for _ in ()).throw(SystemExit(1)))
    discovery.cmd_guard_discover(SimpleNamespace(config_only=True, report=None))
    output = capsys.readouterr().out
    assert "hooks: configured | MCP: configured | gateway: connection_verified" in output
    assert "Upload failed" in output
