"""
Canonical tool group mapping — single source of truth for semantic match_tool names.
Shared across CLI hook, MCP, and API (mirrored at apps/api/app/modules/guard/tool_groups.py).
"""

TOOL_GROUPS: dict[str, set[str]] = {
    "shell":            {"bash", "run_command", "execute", "terminal", "shell"},
    "filesystem-write": {"write", "edit", "write_file", "edit_file", "str_replace_editor"},
    "filesystem-read":  {"read", "read_file", "glob", "grep", "list_directory"},
    "network":          {"web_fetch", "web_search", "http_request", "curl", "fetch"},
}

# Inverted: raw tool name → semantic group
_RAW_TO_GROUP: dict[str, str] = {
    raw: group
    for group, raws in TOOL_GROUPS.items()
    for raw in raws
}


def normalize_tool(tool_name: str) -> str:
    """Map a raw tool name to its semantic group, or return as-is if unknown."""
    return _RAW_TO_GROUP.get(tool_name.lower(), tool_name.lower())


def expand_match_tool(match_tool: str) -> set[str]:
    """
    Expand a match_tool value (semantic group or raw name, comma-separated)
    into the full set of raw tool names it covers.
    """
    result: set[str] = set()
    for token in match_tool.split(","):
        token = token.strip().lower()
        if token == "*":
            return {"*"}
        if token in TOOL_GROUPS:
            result |= TOOL_GROUPS[token]
        else:
            result.add(token)
    return result


def collapse_to_group(match_tool: str) -> str:
    """
    Collapse a comma-separated match_tool value to semantic group names.
    e.g. "write,edit" → "filesystem-write"
         "bash,run_command" → "shell"
         "bash,write" → "shell,filesystem-write"
    """
    if not match_tool or match_tool.strip() == "*":
        return "*"
    tokens = [t.strip().lower() for t in match_tool.split(",") if t.strip()]
    groups_seen: list[str] = []
    for token in tokens:
        group = _RAW_TO_GROUP.get(token, token)
        if group not in groups_seen:
            groups_seen.append(group)
    return ",".join(groups_seen)
