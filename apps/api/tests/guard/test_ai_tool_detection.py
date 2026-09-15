"""Detection precedence for gateway.detect_ai_tool.

Header first, then a substring match against config/ai_tools.json keys,
finally the "unknown" sentinel. The detection function is intentionally
UA-agnostic — it will not match anything the JSON doesn't list.
"""
from __future__ import annotations

from app.guard.gateway import detect_ai_tool, _known_ai_tools


class _Headers:
    """Minimal case-insensitive header stand-in — just enough for the .get
    calls the detector makes."""

    def __init__(self, **kv):
        self._m = {k.lower(): v for k, v in kv.items()}

    def get(self, name, default=None):
        return self._m.get(name.lower(), default)


def test_known_tools_loaded_from_json():
    """Guard against a config regression that empties the tool list."""
    tools = _known_ai_tools()
    assert "claude-code" in tools
    assert "codex-desktop" in tools


def test_explicit_header_wins_over_ua_and_case_folds():
    h = _Headers(**{
        "X-Conduct-Ai-Tool": "codex-desktop",
        "User-Agent": "claude-cli/0.14.7",
    })
    assert detect_ai_tool(h) == "codex-desktop"


def test_ua_substring_matches_json_key():
    h = _Headers(**{"User-Agent": "cursor/2.0 (macOS)"})
    assert detect_ai_tool(h) == "cursor"


def test_ua_without_json_key_is_unknown():
    """UA doesn't contain any listed key → 'unknown' sentinel."""
    h = _Headers(**{"User-Agent": "Mozilla/5.0 something-mystery-client/9"})
    assert detect_ai_tool(h) == "unknown"


def test_no_headers_is_unknown():
    h = _Headers()
    assert detect_ai_tool(h) == "unknown"


def test_empty_header_string_falls_through_to_ua():
    h = _Headers(**{
        "X-Conduct-Ai-Tool": "   ",
        "User-Agent": "windsurf/1.2",
    })
    assert detect_ai_tool(h) == "windsurf"
