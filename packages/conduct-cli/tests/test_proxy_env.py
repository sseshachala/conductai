"""Smoke check for `conduct guard sync` proxy env writer.

Validates:
  - env file written with 3 provider pairs and member token formatted as guard-mt-<…>
  - shell rc source line added exactly once across multiple syncs
  - override flag wins (--proxy-url)
"""
from __future__ import annotations

import os
import json
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
    assert 'export ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy/anthropic"' in env
    assert 'export ANTHROPIC_API_KEY="abc123"' in env
    assert 'export OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai/v1"' in env
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
    assert "env -u ANTHROPIC_BASE_URL" not in rc_text


@pytestmark_posix
def test_sync_removes_generated_claude_proxy_bypass(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")
    zshrc = tmp_path / ".zshrc"
    custom_alias = "alias claude-work='claude --worktree'"
    zshrc.write_text(
        f"{custom_alias}\n{guard.SHELL_RC_MARKER}\n{guard.SHELL_SOURCE_LINE}\n"
        "alias claude='env -u ANTHROPIC_BASE_URL claude'\n"
    )

    _, changed = guard._write_proxy_env("abc", "https://api.conductai.ai/gateway/v1")

    content = zshrc.read_text()
    assert changed is True
    assert "env -u ANTHROPIC_BASE_URL" not in content
    assert custom_alias in content


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
    assert 'ANTHROPIC_BASE_URL="https://my-self-hosted.example.com/proxy/anthropic"' in env
    assert 'OPENAI_BASE_URL="https://my-self-hosted.example.com/proxy/openai/v1"' in env


@pytestmark_posix
def test_env_file_strips_trailing_slash(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.setenv("SHELL", "/bin/zsh")

    guard._write_proxy_env("abc", "https://api.conductai.ai/proxy/")
    env = (tmp_path / ".conduct" / "env").read_text()
    assert 'ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy/anthropic"' in env
    assert 'OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai/v1"' in env


def test_fetched_legacy_proxy_url_maps_to_gateway_v1():
    assert guard._gateway_v1_url("https://api.conductai.ai/proxy") == "https://api.conductai.ai/gateway/v1"
    assert guard._gateway_v1_url("http://localhost:8000/gateway/v1") == "http://localhost:8000/gateway/v1"


def test_configure_codex_proxy_is_secret_free(tmp_path, monkeypatch):
    monkeypatch.setattr(guard.Path, "home", lambda: tmp_path)
    codex = tmp_path / ".codex"
    codex.mkdir()
    config = codex / "config.toml"
    config.write_text('model = "gpt-test"\n')

    assert guard._configure_codex_proxy("https://api.conductai.ai/gateway/v1")
    written = config.read_text()
    assert 'model_provider = "conduct"' in written
    assert 'base_url = "https://api.conductai.ai/gateway/v1/openai/v1"' in written
    assert 'wire_api = "responses"' in written
    assert "cond_agt_" not in written
    assert config.with_suffix(".toml.pre-conduct-proxy").exists()


def test_codex_hook_install_collapses_duplicate_conduct_entries(tmp_path, monkeypatch):
    monkeypatch.setattr(guard.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(guard, "_best_python", lambda: "/usr/bin/python3")
    codex = tmp_path / ".codex"
    codex.mkdir()
    hook_path = tmp_path / ".conduct" / "hook.py"
    stale_hook_path = tmp_path / ".conductguard" / "hook.py"
    hooks_path = codex / "hooks.json"
    duplicate = {"matcher": ".*", "hooks": [{"type": "command", "command": f"python3 {hook_path}"}]}
    stale = {"matcher": ".*", "hooks": [{"type": "command", "command": f"python3 {stale_hook_path}"}]}
    unrelated = {"matcher": "Read", "hooks": [{"type": "command", "command": "other-hook"}]}
    hooks_path.write_text(json.dumps({"hooks": {
        "PreToolUse": [duplicate, duplicate, stale, unrelated],
        "PostToolUse": [duplicate, duplicate, stale],
    }}))

    guard._install_codex_hook(hook_path)
    installed = json.loads(hooks_path.read_text())["hooks"]
    for event in ("PreToolUse", "PostToolUse"):
        commands = [
            item["command"]
            for registration in installed[event]
            for item in registration["hooks"]
        ]
        conduct_commands = [
            command
            for command in commands
            if str(hook_path) in command
        ]
        assert len(conduct_commands) == 1
        assert all(str(stale_hook_path) not in command for command in commands)
    assert installed["PreToolUse"][0] == unrelated


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
    assert '$env:ANTHROPIC_BASE_URL = "https://api.conductai.ai/proxy/anthropic"' in text
    assert '$env:ANTHROPIC_API_KEY  = "abc123"' in text
    assert '$env:OPENAI_BASE_URL = "https://api.conductai.ai/proxy/openai/v1"' in text
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
    assert "$env:ANTHROPIC_BASE_URL=$null" not in text


def test_windows_sync_removes_generated_claude_proxy_bypass(tmp_path, monkeypatch):
    _redirect_home_windows(tmp_path, monkeypatch)
    profile = tmp_path / "Documents" / "PowerShell" / "Microsoft.PowerShell_profile.ps1"
    profile.parent.mkdir(parents=True)
    bypass = next(value for value in guard._LEGACY_CLAUDE_BYPASSES if value.startswith("function claude"))
    profile.write_text(f"{guard.SHELL_RC_MARKER}\n{bypass}\n")

    _, changed = guard._write_proxy_env("abc", "https://api.conductai.ai/gateway/v1")

    assert changed is True
    assert "$env:ANTHROPIC_BASE_URL=$null" not in profile.read_text()


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


# ---------------------------------------------------------------------------
# Regression: _is_anthropic_proxied / _is_openai_proxied must fall back to
# ~/.conduct/env when the env var is missing from the current process.
# `conduct login` writes the file but does not re-source itself, so the
# per-tool coverage table used to report `✗ Not routed` right after login
# even though future shells will route correctly.
# ---------------------------------------------------------------------------

@pytestmark_posix
def test_is_anthropic_proxied_falls_back_to_env_file(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    (tmp_path / ".conduct").mkdir(exist_ok=True)
    (tmp_path / ".conduct" / "env").write_text(
        'export ANTHROPIC_BASE_URL="https://api.conductai.ai/proxy/anthropic"\n'
        'export ANTHROPIC_API_KEY="cond_agt_test"\n'
    )
    assert guard._is_anthropic_proxied() is True


@pytestmark_posix
def test_is_openai_proxied_falls_back_to_env_file(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    (tmp_path / ".conduct").mkdir(exist_ok=True)
    (tmp_path / ".conduct" / "env").write_text(
        'export OPENAI_BASE_URL="https://api.conductai.ai/proxy/openai/v1"\n'
    )
    assert guard._is_openai_proxied() is True


@pytestmark_posix
def test_is_anthropic_proxied_false_when_no_env_and_no_file(tmp_path, monkeypatch):
    _redirect_home(tmp_path, monkeypatch)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    # No ~/.conduct/env written
    assert guard._is_anthropic_proxied() is False
