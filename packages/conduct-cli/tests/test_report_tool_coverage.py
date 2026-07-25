"""Smoke: agent-token header is set on the /guard/developer-tools POST.

Covers both entry points:
- conduct_cli.guard._report_tools_to_server (reads guard config + conduct config)
- conduct_cli.main._report_tool_coverage (reads main conduct config)

These paths had a legacy cond_live_* prefix check that was removed. These tests
lock in the current behavior: prefer the agent-token read, fall back to the
generic 'token' key, never send an Authorization header without a token.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from conduct_cli import guard as guard_mod
from conduct_cli import main as main_mod


# ── guard._report_tools_to_server ─────────────────────────────────────────────

def test_guard_report_prefers_conduct_agent_token_over_guard_token(tmp_path, monkeypatch):
    """When ~/.conduct/config.json has agent_token, it wins over the guard-local token."""
    conduct_dir = tmp_path / ".conduct"
    conduct_dir.mkdir()
    (conduct_dir / "config.json").write_text(json.dumps({"agent_token": "cond_agt_MAIN"}))

    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__  = MagicMock(return_value=False)

    with patch.object(Path, "home", classmethod(lambda cls: tmp_path)), \
         patch.object(guard_mod, "_detect_ai_tools", return_value=[{"name": "cursor"}]), \
         patch.object(guard_mod, "_load_guard_config", return_value={"agent_token": "cond_agt_GUARD", "user_email": "u@x.com"}), \
         patch.object(guard_mod, "_api_url", return_value="https://api.example"), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        guard_mod._report_tools_to_server()

    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer cond_agt_MAIN"


def test_guard_report_falls_back_to_guard_token_when_no_conduct_config(tmp_path, monkeypatch):
    """No ~/.conduct/config.json → use the guard-local token."""
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__  = MagicMock(return_value=False)

    with patch.object(Path, "home", classmethod(lambda cls: tmp_path)), \
         patch.object(guard_mod, "_detect_ai_tools", return_value=[{"name": "cursor"}]), \
         patch.object(guard_mod, "_load_guard_config", return_value={"agent_token": "cond_agt_GUARD", "user_email": "u@x.com"}), \
         patch.object(guard_mod, "_api_url", return_value="https://api.example"), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        guard_mod._report_tools_to_server()

    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer cond_agt_GUARD"


def test_guard_report_no_auth_header_when_no_token(tmp_path, monkeypatch):
    """No tokens anywhere → request goes out but with no Authorization header."""
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__  = MagicMock(return_value=False)

    with patch.object(Path, "home", classmethod(lambda cls: tmp_path)), \
         patch.object(guard_mod, "_detect_ai_tools", return_value=[{"name": "cursor"}]), \
         patch.object(guard_mod, "_load_guard_config", return_value={"agent_token": "", "user_email": "u@x.com"}), \
         patch.object(guard_mod, "_api_url", return_value="https://api.example"), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        guard_mod._report_tools_to_server()

    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") is None


# ── main._report_tool_coverage ────────────────────────────────────────────────

def test_main_report_prefers_agent_token_over_token(monkeypatch):
    """api_key (agent_token field) wins over the generic token key."""
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__  = MagicMock(return_value=False)

    with patch.object(main_mod, "_load_config", return_value={
             "server": "https://api.example",
             "agent_token": "cond_agt_MAIN",
             "token": "should_lose",
             "email": "u@x.com",
         }), \
         patch.object(main_mod, "_detect_ai_tools", return_value=[{"name": "cursor"}]), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        main_mod._report_tool_coverage()

    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer cond_agt_MAIN"


def test_main_report_falls_back_to_token_when_no_agent_token(monkeypatch):
    """No agent_token → use the generic token key."""
    fake_resp = MagicMock()
    fake_resp.__enter__ = lambda s: s
    fake_resp.__exit__  = MagicMock(return_value=False)

    with patch.object(main_mod, "_load_config", return_value={
             "server": "https://api.example",
             "agent_token": "",
             "token": "fallback_tok",
             "email": "u@x.com",
         }), \
         patch.object(main_mod, "_detect_ai_tools", return_value=[{"name": "cursor"}]), \
         patch("urllib.request.urlopen", return_value=fake_resp) as mock_open:
        main_mod._report_tool_coverage()

    req = mock_open.call_args[0][0]
    assert req.get_header("Authorization") == "Bearer fallback_tok"
