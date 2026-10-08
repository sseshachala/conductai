"""Team memory tool labels + native-capture skip list (#2389)."""
from unittest.mock import MagicMock, patch

import pytest

from app.routers import team_memory as tm


@pytest.mark.parametrize("sent,stored", [
    ("claude-code", "claude_code"),   # new CLI surface id → legacy Claude label
    ("claude_code", "claude_code"),   # older CLIs
    ("codex-cli", "codex-cli"),
    ("codex-desktop", "codex-desktop"),
    ("copilot-cli", "copilot-cli"),
])
def test_session_tool_label(sent, stored):
    assert tm.SessionMemoryIn(session_id="s", tool=sent).tool == stored


def test_default_tool_unchanged():
    assert tm.SessionMemoryIn(session_id="s").tool == "claude_code"


def test_natively_captured_tools_skip_synthesis():
    assert {"claude_code", "claude-code", "codex-cli", "codex-desktop", "copilot-cli"} <= tm._HOOK_TOOLS
    # MCP-only / hookless surfaces still rely on synthesis.
    assert not {"cursor", "windsurf", "codex", "claude.ai"} & tm._HOOK_TOOLS


def test_store_session_keeps_codex_label():
    db = MagicMock()
    body = tm.SessionMemoryIn(session_id="s1", tool="codex-cli", repo_full_name="acme/repo",
                              raw_transcript="user: fix retry\n\nassistant: added backoff")
    with patch.object(tm, "_summarise", return_value="Added backoff to retry loop."), \
         patch.object(tm, "set_workspace_rls"):
        result = tm.store_session_memory(body, MagicMock(),
                                         workspace_id="00000000-0000-0000-0000-000000000001", _="ok", db=db)
    row = db.add.call_args.args[0]
    assert row.tool == "codex-cli" and row.repo_full_name == "acme/repo"
    assert result.get("stored", True) is not False


def test_synthesis_excludes_native_tools():
    db = MagicMock()
    db.execute.return_value.fetchall.return_value = []
    with patch.object(tm, "SessionLocal", return_value=db), patch.object(tm, "set_workspace_rls"):
        tm._synthesize_mcp_sessions("00000000-0000-0000-0000-000000000001")
    params = db.execute.call_args.args[1]
    assert "codex-cli" in params["skip_tools"] and "copilot-cli" in params["skip_tools"]
