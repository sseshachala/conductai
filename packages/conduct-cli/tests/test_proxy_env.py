"""Smoke check for `conduct guard sync` proxy env writer.

Validates:
  - env file written with 3 provider pairs and member token formatted as guard-mt-<…>
  - shell rc source line added exactly once across multiple syncs
  - override flag wins (--proxy-url)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

import pytest

from conduct_cli import guard

pytestmark_posix = pytest.mark.skipif(
    sys.platform == "win32",
    reason="shell rc integration is bash/zsh only; windows uses powershell",
)


def _redirect_home(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    # The guard module captures Path.home() at import time into module-level
    # constants. Re-bind them so the redirect actually takes effect.
    monkeypatch.setattr(guard, "CONDUCT_DIR", tmp_path / ".conduct")
    monkeypatch.setattr(guard, "PROXY_ENV_FILE", tmp_path / ".conduct" / "env")


@pytestmark_posix
def test_env_file_written_with_all_three_pairs(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    rc, sourced = guard._write_proxy_env("abc123", "https://api.conductai.ai/proxy")

    env = (tmp_path / ".conduct" / "env").read_text()
    assert 'export ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy"' in env
    assert 'export ANTHROPIC_API_KEY="abc123"' in env
    assert 'export OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai"' in env
    assert 'export OPENAI_API_KEY="abc123"' in env
    assert 'export PERPLEXITY_BASE_URL="https://api.conductai.ai/proxy/perplexity"' in env
    assert 'export PERPLEXITY_API_KEY="abc123"' in env
    assert sourced is True
    assert rc.name == ".zshrc"


@pytestmark_posix
def test_shell_rc_source_line_added_once_across_multiple_syncs(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")
    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")
    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")

    rc_text = (tmp_path / ".zshrc").read_text()
    assert rc_text.count(guard.SHELL_RC_MARKER) == 1
    assert rc_text.count(guard.SHELL_SOURCE_LINE) == 1


@pytestmark_posix
def test_bash_picks_bashrc(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/usr/bin/bash")

    rc, _ = guard._write_proxy_env("xyz", "https://api.conductai.ai/proxy")
    assert rc.name == ".bashrc"
    assert (tmp_path / ".bashrc").exists()


def test_missing_token_returns_empty_path(tmp_path, monkeypatch, capsys):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    rc, sourced = guard._write_proxy_env("", "https://api.conductai.ai/proxy")
    assert rc == Path("")
    assert sourced is False
    assert not (tmp_path / ".conduct" / "env").exists()
    assert "no agent token" in capsys.readouterr().out


@pytestmark_posix
def test_override_url_picked_up(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    guard._write_proxy_env("abc", "https://my-self-hosted.example.com/proxy")
    env = (tmp_path / ".conduct" / "env").read_text()
    assert 'ANTHROPIC_BASE_URL="https://my-self-hosted.example.com/proxy"' in env
    assert 'OPENAI_BASE_URL="https://my-self-hosted.example.com/proxy/openai"' in env


@pytestmark_posix
def test_env_file_strips_trailing_slash(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy/")
    env = (tmp_path / ".conduct" / "env").read_text()
    assert 'ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy"' in env   # no trailing slash
    assert 'OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai"' in env


@pytestmark_posix
def test_unknown_shell_skips_rc_write(tmp_path, monkeypatch, capsys):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/csh")

    rc, sourced = guard._write_proxy_env("abc", "https://x")
    assert rc == Path("")
    assert sourced is False
    # env file IS written even on unknown shell — the user can source manually
    assert (tmp_path / ".conduct" / "env").exists()
    assert "Source manually" in capsys.readouterr().out


# ── Windows branch ────────────────────────────────────────────────────────────

def _redirect_home_windows(tmp_path: Path, monkeypatch):
    """Redirect Path.home() and module-level paths for the Windows branch."""
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(guard, "CONDUCT_DIR", tmp_path / ".conduct")
    monkeypatch.setattr(guard, "PROXY_ENV_FILE", tmp_path / ".conduct" / "env")


def test_windows_writes_ps1_env_file(tmp_path, monkeypatch):
    _redirect_home_windows(tmp_path, monkeypatch)

    guard._write_proxy_env("abc123", "https://api.conductai.ai/proxy")

    ps1 = tmp_path / ".conduct" / "env.ps1"
    assert ps1.exists()
    text = ps1.read_text()
    assert '$env:ANTHROPIC_BASE_URL = "https://api.conductai.ai/proxy"' in text
    assert '$env:ANTHROPIC_API_KEY  = "abc123"' in text
    assert '$env:OPENAI_BASE_URL = "https://api.conductai.ai/proxy/openai"' in text
    assert '$env:OPENAI_API_KEY  = "abc123"' in text
    assert '$env:PERPLEXITY_BASE_URL = "https://api.conductai.ai/proxy/perplexity"' in text
    assert '$env:PERPLEXITY_API_KEY  = "abc123"' in text


def test_windows_appends_source_line_to_powershell_profile_once(tmp_path, monkeypatch):
    _redirect_home_windows(tmp_path, monkeypatch)

    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")
    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")
    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")

    profile = tmp_path / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    assert profile.exists()
    text = profile.read_text()
    assert text.count(guard.SHELL_RC_MARKER) == 1
    assert text.count('. "$HOME/.conduct/env.ps1"') == 1


def test_windows_prefers_ps7_profile_when_no_wps5_exists(tmp_path, monkeypatch):
    _redirect_home_windows(tmp_path, monkeypatch)
    # no existing profile files at all
    assert not (tmp_path / "Documents").exists()

    rc, _ = guard._write_proxy_env("abc", "https://api.conductai.ai/proxy")

    ps7 = tmp_path / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    wps5 = tmp_path / "Documents" / "WindowsPowerShell" / "Microsoft.PowerShell_profile.ps1"
    assert rc == ps7
    assert ps7.exists()
    assert not wps5.exists()
