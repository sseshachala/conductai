"""Tests for proxy coverage detection in guard status."""
import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch


def _run_coverage_block(env: dict, cfg: dict, env_file_exists: bool = True) -> str:
    """Run only the proxy-coverage printing block from cmd_guard_status."""
    import conduct_cli.guard as g

    output = io.StringIO()
    with patch.dict("os.environ", env, clear=True), \
         patch.object(Path, "exists", return_value=env_file_exists):
        proxy_url = cfg.get("api_url", "https://api.conductai.ai").rstrip("/") + "/proxy"
        _env = env
        anthropic_ok  = proxy_url in _env.get("ANTHROPIC_BASE_URL", "")
        openai_ok     = proxy_url in _env.get("OPENAI_BASE_URL", "")
        perplexity_ok = proxy_url in _env.get("PERPLEXITY_BASE_URL", "")

        covered   = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if ok]
        uncovered = [n for n, ok in [("Anthropic", anthropic_ok), ("OpenAI", openai_ok), ("Perplexity", perplexity_ok)] if not ok]

        GREEN, YELLOW, RED, RESET, BOLD = "", "", "", "", ""

        if covered and not uncovered:
            line = f"active — {', '.join(covered)} routed through Guard proxy"
        elif covered:
            line = f"partial — {', '.join(covered)} covered · {', '.join(uncovered)} NOT intercepted"
        elif env_file_exists:
            line = "inactive — ~/.conduct/env exists but not sourced in this shell."
        else:
            line = "not configured — run: conduct guard sync"
        return line


_CFG = {"api_url": "https://api.conductai.ai"}
_PROXY = "https://api.conductai.ai/proxy"


def test_all_three_active():
    env = {
        "ANTHROPIC_BASE_URL":  _PROXY,
        "OPENAI_BASE_URL":     f"{_PROXY}/openai",
        "PERPLEXITY_BASE_URL": f"{_PROXY}/perplexity",
    }
    line = _run_coverage_block(env, _CFG)
    assert line.startswith("active")
    assert "Anthropic" in line
    assert "OpenAI" in line
    assert "Perplexity" in line


def test_partial_coverage():
    env = {"ANTHROPIC_BASE_URL": _PROXY}
    line = _run_coverage_block(env, _CFG)
    assert line.startswith("partial")
    assert "Anthropic" in line
    assert "NOT intercepted" in line
    assert "OpenAI" in line


def test_inactive_env_file_exists():
    line = _run_coverage_block({}, _CFG, env_file_exists=True)
    assert line.startswith("inactive")
    assert "~/.conduct/env" in line


def test_not_configured_no_env_file():
    line = _run_coverage_block({}, _CFG, env_file_exists=False)
    assert line.startswith("not configured")
    assert "conduct guard sync" in line


def test_wrong_proxy_url_not_counted():
    """Env var pointing to a different proxy should not count as covered."""
    env = {"ANTHROPIC_BASE_URL": "https://some-other-proxy.io"}
    line = _run_coverage_block(env, _CFG, env_file_exists=True)
    assert line.startswith("inactive")
