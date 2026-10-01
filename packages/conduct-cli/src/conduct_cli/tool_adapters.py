"""Read-only adapter contract. Configured commands are data, never discovery code."""
from dataclasses import dataclass
import os
from pathlib import Path

from .tool_catalog import TOOLS


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

    def root(self):
        default = Path.home().joinpath(*self.home_parts)
        return Path(os.environ.get(self.home_env, str(default))).expanduser() if self.home_env else default

    def mcp_sources(self, project=None):
        root = self.root()
        if self.id == "claude-code":
            # settings.json is retained for older Conduct-written entries.
            sources = [ConfigSource(root / "settings.json", "legacy-user"),
                       ConfigSource(root.parent / (root.name + ".json"), "user")]
            project_file = ".mcp.json"
        elif self.id == "codex":
            sources = [ConfigSource(root / "config.toml", "user", "mcp_servers")]
            project_file = ".codex/config.toml"
        elif self.id == "cursor":
            sources = [ConfigSource(root / "mcp.json", "user")]
            project_file = ".cursor/mcp.json"
        elif self.id == "windsurf":
            sources = [ConfigSource(root / "mcp_config.json", "user")]
            project_file = None
        else:
            sources = [ConfigSource(root / "mcp-config.json", "user")]
            project_file = None
        if project is not None and project_file:
            project = Path(project).resolve()
            path = project / project_file
            path.resolve().relative_to(project)
            sources.append(ConfigSource(path, "project", "mcp_servers" if self.id == "codex" else "mcpServers"))
        return sources


ADAPTERS = {
    "claude-code": ToolAdapter("claude-code", (".claude",), "CLAUDE_CONFIG_DIR"),
    "codex": ToolAdapter("codex", (".codex",), "CODEX_HOME"),
    "cursor": ToolAdapter("cursor", (".cursor",)),
    "windsurf": ToolAdapter("windsurf", (".codeium", "windsurf")),
    "copilot-cli": ToolAdapter("copilot-cli", (".copilot",), "COPILOT_HOME"),
}
if set(ADAPTERS) != set(TOOLS):
    raise ValueError("Every catalog tool must have a registered adapter")
