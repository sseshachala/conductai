import argparse
import importlib.util
from pathlib import Path
from unittest.mock import Mock

import pytest

spec = importlib.util.spec_from_file_location("transport_checks_tested", Path(__file__).with_name("transport_checks.py"))
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


@pytest.mark.parametrize("target,url", [
    ("local", "https://localhost:3444"), ("local", "http://127.0.0.1:3100"),
    ("saas", "https://api.conductai.ai"),
])
def test_valid_target(target, url):
    checks.validate_target({"api_url": url}, target)


@pytest.mark.parametrize("target,config", [
    ("local", {"api_url": "https://api.conductai.ai"}),
    ("saas", {"api_url": "https://localhost:3444"}),
    ("local", {"api_url": "https://localhost:3444", "mcp_url": "https://api.conductai.ai/mcp"}),
    ("saas", {"api_url": "https://api.conductai.ai.evil.test"}),
    ("saas", {"api_url": "https://api.conductai.ai:9999"}),
    ("local", {"api_url": "https://user:secret@localhost:3444"}),
])
def test_cross_deployment_or_invalid_endpoint_rejected(target, config):
    with pytest.raises(ValueError):
        checks.validate_target(config, target)


def test_shared_runner_forwards_options_without_copying_credentials(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text('{"api_url":"https://localhost:3444"}')
    parser = argparse.ArgumentParser()
    checks.add_arguments(parser)
    args = parser.parse_args(["--transport-config", str(config), "--transport-ca", "test-ca.crt",
                             "--inference", "--litellm-url", "http://localhost:4000/v1", "--model", "test-model"])
    module = checks.smoke_module()
    module.main = Mock(return_value=0)
    monkeypatch.setattr(checks, "smoke_module", lambda: module)
    assert checks.run(args, "local") == 0
    argv = module.main.call_args.args[0]
    assert "--inference" in argv
    assert argv[argv.index("--ca") + 1] == "test-ca.crt"
    assert argv[argv.index("--config") + 1] == str(config)


def test_missing_config_rejected():
    parser = argparse.ArgumentParser()
    checks.add_arguments(parser)
    with pytest.raises(ValueError, match="transport-config"):
        checks.validate_arguments(parser.parse_args([]), "local")
