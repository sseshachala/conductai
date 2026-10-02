import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conduct_cli.guard_commands import copilot, gateway

TOKEN = "cond_agt_test_only"
URL = "https://gateway.example/gateway/v1"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("SHELL", "/bin/bash")
    monkeypatch.setattr(gateway, "CONDUCT_DIR", tmp_path / ".conduct")
    monkeypatch.setattr(gateway, "PROXY_ENV_FILE", tmp_path / ".conduct/env")
    for name in list(os.environ):
        if name.startswith(copilot.PREFIX):
            monkeypatch.delenv(name)
    return tmp_path


def cfg(token=TOKEN, url=URL):
    return {"api_url": "https://api.example", "gateway_url": url, "agent_token": token}


@pytest.mark.parametrize("platform,filename", [("linux", "env"), ("win32", "env.ps1")])
def test_managed_file_rotation_and_disable(home, monkeypatch, platform, filename):
    monkeypatch.setattr(sys, "platform", platform)
    gateway._write_proxy_env(TOKEN, URL)
    path = home / ".conduct" / filename
    first = path.read_text()
    assert "COPILOT_PROVIDER_WIRE_MODEL" not in first
    assert "COPILOT_MODEL=" not in first
    assert copilot.configured(cfg())
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0
    gateway._write_proxy_env(TOKEN, URL)
    assert path.read_text() == first
    gateway._write_proxy_env(TOKEN + "_new", URL + "/new")
    assert not copilot.configured(cfg())
    assert copilot.configured(cfg(TOKEN + "_new", URL + "/new"))
    gateway._write_proxy_env(TOKEN, URL, copilot=False)
    assert not copilot.configured(cfg())


@pytest.mark.parametrize("change", [{"BASE_URL": "https://gateway.example.evil/gateway/v1/openai/v1"},
    {"BEARER_TOKEN": "cond_agt_stale"}, {"TYPE": "anthropic"}, {"WIRE_API": "chat"},
    {"WIRE_MODEL": "balanced"}, {"API_KEY": "provider-key"}, {"BASE_URL": ""}])
def test_process_overrides_fail_closed(home, monkeypatch, change):
    gateway._write_proxy_env(TOKEN, URL)
    values = copilot.read_values(home / ".conduct/env")
    values.update({copilot.PREFIX + key: value for key, value in change.items()})
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert not copilot.configured(cfg())


def test_valid_process_configuration(home, monkeypatch):
    for key, value in {"BASE_URL": URL + "/openai/v1", "TYPE": "openai", "WIRE_API": "responses",
                       "BEARER_TOKEN": TOKEN}.items():
        monkeypatch.setenv(copilot.PREFIX + key, value)
    assert copilot.configured(cfg())


@pytest.mark.parametrize("platform,filename,literal,dynamic", [
    ("linux", "env-override", 'export COPILOT_PROVIDER_BASE_URL="https://custom.example"\n',
     'export COPILOT_PROVIDER_BASE_URL="$(anything)"\n'),
    ("win32", "env-override.ps1", "$env:COPILOT_PROVIDER_BASE_URL = 'https://custom.example'\n",
     '$env:COPILOT_PROVIDER_BASE_URL = "$(anything)"\n'),
])
def test_overrides_preserved_and_dynamic_values_unknown(home, monkeypatch, platform, filename, literal, dynamic):
    monkeypatch.setattr(sys, "platform", platform)
    gateway._write_proxy_env(TOKEN, URL)
    override = home / ".conduct" / filename
    override.write_text(literal)
    gateway._write_proxy_env(TOKEN, URL)
    assert "https://custom.example" in override.read_text()
    assert not copilot.configured(cfg())
    override.write_text(dynamic)
    assert not copilot.configured(cfg())


@pytest.mark.skipif(os.name == "nt" or not shutil.which("bash"), reason="Requires native POSIX shell")
def test_posix_sourcing_model_selection_and_disable(home):
    gateway._write_proxy_env(TOKEN, URL)
    code = '. "$HOME/.conduct/env"; printf "%s|%s|%s" "$COPILOT_MODEL" "$COPILOT_PROVIDER_WIRE_MODEL" "$COPILOT_PROVIDER_WIRE_API"'
    result = subprocess.run(["bash", "-c", code], env={**os.environ, "COPILOT_MODEL": "selected-model"},
                            capture_output=True, text=True, check=True)
    assert result.stdout == "selected-model||responses"
    gateway._write_proxy_env(TOKEN, URL, copilot=False)
    result = subprocess.run(["bash", "-c", '. "$HOME/.conduct/env"; printf "%s" "$COPILOT_PROVIDER_BEARER_TOKEN"'],
                            env={**os.environ, "COPILOT_PROVIDER_BEARER_TOKEN": TOKEN}, capture_output=True, text=True)
    assert result.stdout == ""


def test_custom_deployment_without_gateway_not_routed(home):
    gateway._write_proxy_env(TOKEN, URL)
    assert not copilot.configured({"api_url": "https://api.example", "agent_token": TOKEN})


@pytest.mark.parametrize("platform,filename", [("linux", "env"), ("win32", "env.ps1")])
@pytest.mark.parametrize("default_encoding", ["utf-8", "cp1252"])
def test_clear_managed_preserves_other_providers_and_overrides(home, monkeypatch, platform, filename, default_encoding):
    read_text = Path.read_text
    def locale_read_text(path, *args, **kwargs):
        if not args and kwargs.get("encoding") is None:
            kwargs["encoding"] = default_encoding
        return read_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", locale_read_text)
    monkeypatch.setattr(sys, "platform", platform)
    gateway._write_proxy_env(TOKEN, URL)
    path = home / ".conduct" / filename
    original = path.read_text()
    override = home / ".conduct/env-override"
    override.write_text("# user-owned configuration\n")
    copilot.clear_managed()
    content = path.read_text()
    assert not copilot.configured(cfg())
    assert override.read_text() == "# user-owned configuration\n"
    for line in original.splitlines():
        if copilot.PREFIX not in line:
            assert line in content
    copilot.clear_managed()
    assert path.read_text() == content
    if os.name != "nt":
        assert path.stat().st_mode & 0o077 == 0


def test_clear_managed_does_not_touch_unmanaged_file(home):
    path = home / ".conduct/env"
    path.parent.mkdir()
    content = "export COPILOT_PROVIDER_BEARER_TOKEN=user-owned\n"
    path.write_text(content)
    copilot.clear_managed()
    assert path.read_text() == content


@pytest.mark.skipif(os.name != "nt", reason="Requires native Windows PowerShell")
def test_powershell_sourcing_model_selection_and_disable(home):
    shell = shutil.which("pwsh") or shutil.which("powershell")
    assert shell, "Windows CI requires PowerShell"
    gateway._write_proxy_env(TOKEN, URL)
    path = str(home / ".conduct/env.ps1").replace("'", "''")
    command = f". '{path}'; Write-Output \"$env:COPILOT_MODEL|$env:COPILOT_PROVIDER_WIRE_MODEL|$env:COPILOT_PROVIDER_WIRE_API\""
    result = subprocess.run([shell, "-NoProfile", "-Command", command],
                            env={**os.environ, "COPILOT_MODEL": "selected-model"},
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == "selected-model||responses"
    gateway._write_proxy_env(TOKEN, URL, copilot=False)
    result = subprocess.run([shell, "-NoProfile", "-Command", f". '{path}'; Write-Output $env:COPILOT_PROVIDER_BEARER_TOKEN"],
                            env={**os.environ, "COPILOT_PROVIDER_BEARER_TOKEN": TOKEN},
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == ""
