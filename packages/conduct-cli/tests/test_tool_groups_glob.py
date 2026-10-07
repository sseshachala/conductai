"""CLI mirror of tool_matches: globs like ``mcp__*memory*`` match MCP tool names."""
from conduct_cli.tool_groups import tool_matches


def test_glob_matches_mcp_prefixed_tool() -> None:
    assert tool_matches("mcp__demo__memory_save", "mcp__*memory*,memory_save")
    assert not tool_matches("mcp__demo__search_web", "mcp__*memory*,memory_save")


def test_groups_and_exact_names_unchanged() -> None:
    assert tool_matches("bash", "shell")
    assert tool_matches("Bash", "shell")
    assert not tool_matches("memory_saver", "memory_save")
    assert tool_matches("x", None)
