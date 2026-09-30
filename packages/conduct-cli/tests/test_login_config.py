from types import SimpleNamespace
from unittest.mock import patch
import json

import pytest

from conduct_cli.login_config import endpoints, origin

API = "https://api.conductai.ai"
WEB = "https://app.conductai.ai"


def resolve(config=None, **kwargs):
    return endpoints(SimpleNamespace(**kwargs), config or {}, API, WEB)


def test_saas_defaults():
    assert resolve() == (API, WEB)


def test_custom_server_requires_explicit_console():
    with pytest.raises(ValueError, match="--web-url"):
        resolve(server="https://localhost:3444")


def test_custom_endpoints_and_trailing_slash():
    assert resolve(server="https://localhost:3444/", web_url="https://localhost:3443/") == (
        "https://localhost:3444", "https://localhost:3443")


def test_saved_deployment_is_reused():
    assert resolve({"api_url": "https://api.internal", "web_url": "https://console.internal"}) == (
        "https://api.internal", "https://console.internal")


def test_saved_console_does_not_cross_servers():
    with pytest.raises(ValueError, match="--web-url"):
        resolve({"api_url": "https://api.one", "web_url": "https://console.one"}, server="https://api.two")


def test_manual_token_needs_no_console():
    assert resolve(server="https://api.internal", token="synthetic") == ("https://api.internal", None)


@pytest.mark.parametrize("value", ["http://enterprise.test", "https://user:pass@host.test",
    "https://host.test/path", "https://host.test?x=1", "https://host.test/#frag", "https://host.test:bad"])
def test_unsafe_origins_rejected(value):
    with pytest.raises(ValueError):
        origin(value)


def test_login_persists_endpoints_without_cross_server_restore_or_sync(tmp_path):
    from conduct_cli import main as cli
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"api_url": API, "workspace_id": "old", "refresh_token": "old-fixture"}))
    args = SimpleNamespace(server="https://localhost:3444", web_url="https://localhost:3443",
                           token=None, no_sync=True)
    with patch.object(cli, "CONFIG_PATH", path), patch.object(cli, "_web_login_flow",
            return_value={"agent_token": "synthetic", "workspace_id": "new"}) as login, \
            patch.object(cli.api, "req", return_value=[]) as request, \
            patch("conduct_cli.guard.cmd_guard_sync") as sync:
        cli.cmd_login(args)
    login.assert_called_once_with(args.server, args.web_url)
    sync.assert_not_called()
    assert all(call.args[0] != "POST" for call in request.call_args_list)
    saved = json.loads(path.read_text())
    assert saved["web_url"] == args.web_url
    assert saved["workspace_id"] == "new"
    assert "refresh_token" not in saved
