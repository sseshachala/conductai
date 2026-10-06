"""Read-only adapter contract. Configured commands are data, never discovery code."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from .tool_catalog import TOOLS


# Conduct's MCP server key in every tool config. Older CLIs wrote "conduct-guard"
# (Copilot) and "conductguard" (retired binary); guard sync renames them.
CONDUCT_MCP_KEY = "conduct"
LEGACY_MCP_KEYS = ("conduct-guard", "conductguard")


@dataclass(frozen=True)
class ConfigSource:
    path: Path
    scope: str
    key: str = "mcpServers"


@dataclass(frozen=True)
class ToolAdapter:
    id: str
    home_parts: tuple
    home_env: str = ""
    sources: tuple = ()
    platforms: tuple = ("darwin", "linux", "win32")
    hooks: str | None = None
    usage: str | None = None

    @classmethod
    def from_manifest(cls, tool):
        """Only built-in readers are selectable; manifests never load executable code."""
        spec = tool.get("adapter")
        required = {"version", "platforms", "home", "home_env", "mcp", "hooks", "usage"}
        if (not isinstance(spec, dict) or set(spec) != required
                or type(spec["version"]) is not int or spec["version"] != 1):
            raise ValueError("Unsupported tool adapter contract")
        home = spec["home"]
        if not isinstance(home, list) or not home or any(not _relative_path(p, segment=True) for p in home):
            raise ValueError("Invalid tool home")
        variable = spec["home_env"]
        if variable is not None and (not isinstance(variable, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", variable)):
            raise ValueError("Invalid tool home variable")
        platforms = spec["platforms"]
        if (not isinstance(platforms, list) or not platforms
                or any(p not in ("darwin", "linux", "win32") for p in platforms)
                or len(set(platforms)) != len(platforms)):
            raise ValueError("Invalid tool platforms")
        if (spec["hooks"] not in (None, "claude", "codex", "cursor", "windsurf", "copilot")
                or spec["usage"] not in (None, "claude-jsonl", "codex-jsonl", "copilot-jsonl")):
            raise ValueError("Unknown tool handler")
        sources = spec["mcp"]
        if not isinstance(sources, list) or not sources:
            raise ValueError("Missing MCP sources")
        descriptors = []
        for source in sources:
            if not isinstance(source, dict) or set(source) != {"anchor", "path", "scope", "key"}:
                raise ValueError("Invalid MCP source")
            anchor, path, scope, key = (source[field] for field in ("anchor", "path", "scope", "key"))
            if anchor not in ("root", "root-sibling", "project") or not _relative_path(path) or key not in ("mcpServers", "mcp_servers"):
                raise ValueError("Invalid MCP source location")
            allowed_scopes = ("project",) if anchor == "project" else ("user", "legacy-user")
            if scope not in allowed_scopes:
                raise ValueError("Invalid MCP source scope")
            if anchor == "root-sibling" and path != ".json":
                raise ValueError("Unsupported sibling configuration")
            descriptor = (anchor, path, scope, key)
            if descriptor in descriptors:
                raise ValueError("Duplicate MCP source")
            descriptors.append(descriptor)
        return cls(tool["id"], tuple(home), variable or "", tuple(descriptors),
                   tuple(platforms), spec["hooks"], spec["usage"])

    def root(self):
        default = Path.home().joinpath(*self.home_parts)
        return Path(os.environ.get(self.home_env, str(default))).expanduser() if self.home_env else default

    def mcp_sources(self, project=None):
        root = self.root()
        sources = []
        for anchor, filename, scope, key in self.sources:
            if anchor == "project":
                if project is None:
                    continue
                selected = Path(project).resolve()
                path = selected / filename
                path.resolve().relative_to(selected)
            elif anchor == "root-sibling":
                path = root.parent / (root.name + filename)
            else:
                path = root / filename
            sources.append(ConfigSource(path, scope, key))
        return sources


def _relative_path(value, segment=False):
    if not isinstance(value, str) or not re.fullmatch(r"[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*", value):
        return False
    return all(part not in (".", "..") for part in value.split("/")) and (not segment or "/" not in value)


ADAPTERS = {tool_id: ToolAdapter.from_manifest(tool) for tool_id, tool in TOOLS.items()}
