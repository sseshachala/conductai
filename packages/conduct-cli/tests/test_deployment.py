"""Deployment isolation for persisted endpoints and generated tool settings."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conduct_cli import deployment, log_util
from conduct_cli.guard_commands import gateway, mcp, routing, shared

CUSTOM = {"api_url": "https://api.example.test", "web_url": "https://console.example.test",
          "gateway_url": "https://llm.example.test/gateway/v1",
          "mcp_url": "https://mcp.example.test/mcp"}


def test_saas_defaults():
    selected = deployment.resolve({})
    assert selected.api == deployment.SAAS_API
    assert selected.web == deployment.SAAS_WEB
    assert selected.gateway == deployment.SAAS_GATEWAY
    assert selected.mcp == deployment.SAAS_MCP == "https://gateway.conductai.ai/mcp"


@pytest.mark.parametrize("saved", [deployment.LEGACY_SAAS_MCP, deployment.LEGACY_SAAS_MCP + "/"])
def test_saved_legacy_hosted_mcp_moves_to_gateway(saved):
    # Pre-#2360 CLIs persisted api.conductai.ai/mcp as mcp_url on every guard sync.
    assert deployment.resolve({"mcp_url": saved}).mcp == deployment.SAAS_MCP


def test_hosted_mcp_default_applies_to_generated_bridge(monkeypatch):
    from conduct_cli import main
    monkeypatch.setattr(main, "_load_config", lambda: {})
    args = main._mcp_remote_args(deployment.SAAS_API, "cond_agt_synthetic")
    assert deployment.SAAS_MCP in args and deployment.LEGACY_SAAS_MCP not in args


def test_custom_defaults_never_guess_hosted_services():
    selected = deployment.resolve({"server": CUSTOM["api_url"]})
    assert selected.web is None
    assert selected.gateway is None
    assert selected.mcp == CUSTOM["api_url"] + "/mcp"


@pytest.mark.parametrize("field", ["web_url", "gateway_url", "mcp_url"])
def test_custom_rejects_stale_saas_endpoint(field):
    with pytest.raises(ValueError):
        deployment.resolve({**CUSTOM, field: deployment.SAAS_GATEWAY})


@pytest.mark.parametrize("value", ["https://u:p@example.test/x", "https://example.test/x?q=1",
                                   "https://example.test/../x", 'https://example.test/$(id)',
                                   'https://example.test/`id`', 'https://example.test/"'])
def test_service_url_rejects_unsafe_values(value):
    with pytest.raises(ValueError):
        deployment.service_url(value, CUSTOM["api_url"])


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(shared, "GUARD_DIR", tmp_path / ".conduct")
    monkeypatch.delenv("CONDUCT_PROXY_URL", raising=False)
    monkeypatch.delenv("CONDUCT_API_URL", raising=False)
    return tmp_path


def test_missing_metadata_skips_gateway_or_rejects_stale_files(isolated, monkeypatch):
    monkeypatch.setattr(routing.urllib.request, "urlopen", Mock(side_effect=OSError))
    cfg = {"api_url": CUSTOM["api_url"]}
    assert routing.resolve_routing(cfg, SimpleNamespace()) is None
    shared.GUARD_DIR.mkdir()
    (shared.GUARD_DIR / "env").write_text("old settings")
    with pytest.raises(ValueError, match="managed routing"):
        routing.resolve_routing(cfg, SimpleNamespace())
    assert (shared.GUARD_DIR / "env").read_text() == "old settings"


def test_custom_rejects_hosted_metadata():
    with pytest.raises(ValueError):
        deployment.gateway_from_metadata({"api_url": CUSTOM["api_url"]},
                                         {"conduct_proxy_url": deployment.SAAS_GATEWAY})


def test_explicit_gateway_skips_discovery(isolated, monkeypatch):
    request = Mock(side_effect=AssertionError("unexpected request"))
    monkeypatch.setattr(routing.urllib.request, "urlopen", request)
    assert routing.resolve_routing(CUSTOM, SimpleNamespace()) == CUSTOM["gateway_url"]
    request.assert_not_called()


def test_generated_codex_and_mcp_use_selected_endpoints(isolated, monkeypatch):
    (isolated / ".codex").mkdir()
    assert gateway._configure_codex_proxy(CUSTOM["gateway_url"])
    contents = (isolated / ".codex/config.toml").read_text()
    assert CUSTOM["gateway_url"] + "/openai/v1" in contents
    assert "conductai.ai" not in contents
    monkeypatch.setattr(shared, "_load_guard_config", lambda: CUSTOM)
    assert mcp._deployment(CUSTOM["api_url"]).mcp == CUSTOM["mcp_url"]
    path = isolated / "mcp.json"
    path.write_text(json.dumps({"mcpServers": {"conduct-guard": {
        "type": "http", "url": "https://api.conductai.ai/mcp", "oauth": {"clientId": "old"}}}}))
    mcp._write_mcp_file(path, "conduct-guard", {"type": "http", "url": CUSTOM["mcp_url"]}, None, "test")
    assert json.loads(path.read_text())["mcpServers"]["conduct-guard"] == {
        "type": "http", "url": CUSTOM["mcp_url"]}


def test_telemetry_uses_saved_deployment_and_rejects_env_override(isolated, monkeypatch):
    path = isolated / "config.json"
    path.write_text(json.dumps({**CUSTOM, "member_token": "synthetic", "workspace_id": "test"}))
    monkeypatch.setattr(log_util, "_CONFIG", path)
    send = Mock()
    monkeypatch.setattr(log_util.urllib.request, "urlopen", send)
    log_util._post_event_sync("error", "test", None, {})
    assert send.call_args.args[0].full_url.startswith(CUSTOM["api_url"] + "/")
    send.reset_mock()
    monkeypatch.setenv("CONDUCT_API_URL", deployment.SAAS_API)
    log_util._post_event_sync("error", "test", None, {})
    send.assert_not_called()


def test_receipts_require_custom_console(monkeypatch):
    from conduct_cli.hooks import base
    cfg = {"api_url": CUSTOM["api_url"], "workspace_id": "test"}
    monkeypatch.setattr(base, "load_config", lambda: cfg)
    assert base.hook_receipt_url("receipt") is None
    cfg["web_url"] = CUSTOM["web_url"]
    assert base.hook_receipt_url("receipt") == CUSTOM["web_url"] + "/theguard/blocks/receipt"


@pytest.mark.parametrize("windows", [False, True])
def test_generated_shell_env_uses_custom_gateway(isolated, monkeypatch, windows):
    directory = isolated / ".conduct"
    monkeypatch.setattr(gateway, "CONDUCT_DIR", directory)
    monkeypatch.setattr(gateway, "PROXY_ENV_FILE", directory / "env")
    monkeypatch.setenv("SHELL", "/bin/zsh")
    writer = gateway._write_proxy_env_windows if windows else gateway._write_proxy_env
    writer("cond_agt_synthetic", CUSTOM["gateway_url"])
    content = (directory / ("env.ps1" if windows or gateway.sys.platform == "win32" else "env")).read_text()
    assert CUSTOM["gateway_url"] + "/anthropic" in content
    assert CUSTOM["gateway_url"] + "/openai/v1" in content
    assert "conductai.ai" not in content


def test_gateway_probe_never_uses_hosted_origin(isolated, monkeypatch):
    from conduct_cli.guard_commands import inventory
    connection = Mock()
    connection.getresponse.return_value.status = 401
    transport = Mock(return_value=connection)
    monkeypatch.setattr(inventory.http.client, "HTTPSConnection", transport)
    report = {"agents": [{"framework": "codex", "evidence": {"gateway_configured": True}}]}
    inventory.verify_gateway(report, "cond_agt_synthetic", CUSTOM)
    transport.assert_called_once_with("llm.example.test", timeout=8)
    assert connection.request.call_args.args[:2] == ("GET", "/gateway/v1/openai/v1/models")


def test_dry_run_does_not_refresh_tokens_or_install_packages(monkeypatch):
    from conduct_cli.guard_commands import setup, policy
    monkeypatch.setattr(shared, "_require_guard_config", lambda: {"workspace_id": "test"})
    monkeypatch.setattr(shared, "_req", lambda *a, **kw: {"rules": []})
    monkeypatch.setattr(policy, "_load_policy", lambda: {"rules": []})
    refresh, upgrade = Mock(), Mock()
    monkeypatch.setattr(setup, "_proactive_token_refresh", refresh)
    monkeypatch.setattr(setup, "_check_and_upgrade_packages", upgrade)
    setup.cmd_guard_sync(SimpleNamespace(dry_run=True))
    refresh.assert_not_called()
    upgrade.assert_not_called()


def test_server_override_cannot_reuse_saved_credentials(monkeypatch):
    from conduct_cli import main
    monkeypatch.setattr(main, "_load_config", lambda: {
        **CUSTOM, "workspace_id": "test", "agent_token": "synthetic"})
    with pytest.raises(SystemExit):
        main._require_auth(SimpleNamespace(server=deployment.SAAS_API, token=None))


def test_hosted_mcp_move_updates_bearer_entries_but_preserves_native_oauth(isolated):
    new = {"type": "http", "url": deployment.SAAS_MCP, "headers": {"Authorization": "Bearer cond_agt_synthetic"}}
    bearer = isolated / "bearer.json"
    bearer.write_text(json.dumps({"mcpServers": {"conduct-guard": {**new, "url": deployment.LEGACY_SAAS_MCP}}}))
    mcp._write_mcp_file(bearer, "conduct-guard", new, None, "test")
    assert json.loads(bearer.read_text())["mcpServers"]["conduct-guard"]["url"] == deployment.SAAS_MCP

    # OAuth resource metadata still names api.conductai.ai/mcp — keep the existing sign-in.
    oauth_entry = {"type": "http", "url": deployment.LEGACY_SAAS_MCP, "oauth": {"clientId": "kept"}}
    oauth = isolated / "oauth.json"
    oauth.write_text(json.dumps({"mcpServers": {"conduct-guard": oauth_entry}}))
    mcp._write_mcp_file(oauth, "conduct-guard", new, None, "test")
    assert json.loads(oauth.read_text())["mcpServers"]["conduct-guard"] == oauth_entry
