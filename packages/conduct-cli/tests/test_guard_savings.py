"""
Tests for `conduct guard savings` CLI command (cmd_guard_savings).

Mocks _req and _require_guard_config to avoid real network calls.
Verifies output formatting for various API response shapes.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure conduct_cli package is importable
HERE = Path(__file__).resolve()
CLI_PKG = HERE.parent.parent / "src"
if str(CLI_PKG) not in sys.path:
    sys.path.insert(0, str(CLI_PKG))


def _args():
    return types.SimpleNamespace()


_FAKE_CFG = {
    "workspace_id": "ws-abc-123",
    "api_key": "cond_live_test",
    "api_url": "https://api.example.com",
}

_TEAM_RESPONSE = {
    "workspace_id": "ws-abc-123",
    "developer_count": 2,
    "total_tokens_saved": 1_500_000,
    "total_cost_saved_usd": 8.1,
    "per_day_usd": 8.10,
    "per_month_usd": 243.00,
    "per_year_usd": 2956.50,
    "tools_installed": ["rtk", "booster"],
}


@pytest.fixture(autouse=True)
def patch_config_and_url(monkeypatch):
    """Patch _require_guard_config and _api_url for all tests in this module."""
    import conduct_cli.guard as g
    monkeypatch.setattr(g, "_require_guard_config", lambda: _FAKE_CFG)
    monkeypatch.setattr(g, "_api_url", lambda cfg: cfg.get("api_url", ""))


class TestCmdGuardSavingsOutput:
    def test_prints_team_header(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Team Token Savings" in out

    def test_prints_developer_count(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "2 developer" in out

    def test_prints_total_tokens_formatted(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        # 1_500_000 formatted with commas
        assert "1,500,000" in out

    def test_prints_per_day_amount(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "8.10" in out
        assert "/day" in out

    def test_prints_per_month_amount(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "243" in out
        assert "/month" in out

    def test_prints_per_year_amount(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "2,956" in out or "2957" in out
        assert "/year" in out

    def test_prints_tools_contributing(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "rtk" in out
        assert "booster" in out

    def test_prints_avg_per_developer(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=_TEAM_RESPONSE):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Avg per developer" in out
        # 1_500_000 // 2 = 750_000
        assert "750,000" in out


class TestCmdGuardSavingsZeroDevelopers:
    def test_zero_developer_count(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, developer_count=0, total_tokens_saved=0, per_day_usd=0.0, per_month_usd=0.0, per_year_usd=0.0)
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Team Token Savings" in out
        assert "0 developer" in out

    def test_no_avg_line_when_no_developers(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, developer_count=0, total_tokens_saved=0, per_day_usd=0.0)
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Avg per developer" not in out

    def test_no_tools_line_when_empty(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, developer_count=0, tools_installed=[])
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Tools contributing" not in out


class TestCmdGuardSavingsToolsFilter:
    def test_rtk_only_tools(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, tools_installed=["rtk"])
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "rtk" in out
        assert "booster" not in out

    def test_booster_only_tools(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, tools_installed=["booster"])
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "booster" in out
        assert "rtk" not in out.split("Tools contributing")[1] if "Tools contributing" in out else True


class TestCmdGuardSavingsApiFailure:
    def test_non_dict_response_prints_error(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value=None):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Failed" in out

    def test_string_response_prints_error(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", return_value="error"):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Failed" in out

    def test_network_error_prints_error(self, capsys):
        import conduct_cli.guard as g
        with patch.object(g, "_req", side_effect=ConnectionError("timeout")):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        assert "Failed" in out

    def test_single_developer_singular_label(self, capsys):
        import conduct_cli.guard as g
        resp = dict(_TEAM_RESPONSE, developer_count=1, total_tokens_saved=750_000)
        with patch.object(g, "_req", return_value=resp):
            g.cmd_guard_savings(_args())
        out = capsys.readouterr().out
        # "1 developer" not "1 developers"
        assert "1 developer" in out
        assert "1 developers" not in out
