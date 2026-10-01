"""Passive MCP configuration metadata, with no credentials or endpoint disclosure."""
import hashlib
import json
import re

from conduct_cli.tool_adapters import ADAPTERS

MAX_SERVERS = 100


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def summarize_servers(tool, installation, read_document, project=None):
    records = []
    for source in ADAPTERS[tool].mcp_sources(project):
        document = read_document(source.path)
        servers = document.get(source.key, {})
        if not isinstance(servers, dict):
            raise ValueError("Invalid MCP server map")
        for name, entry in servers.items():
            if len(records) >= MAX_SERVERS:
                raise ValueError("MCP inventory limit exceeded")
            if not isinstance(entry, dict):
                raise ValueError("Invalid MCP server entry")
            # Identifiers only: never upload arbitrary labels, URLs, argv or env.
            safe_name = name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]{0,63}", name) else "redacted"
            if re.match(r"(?i)(cond_|sk[-_]|gh[pousr]_|github_pat_|xox[baprs]-|AKIA)", safe_name):
                safe_name = "redacted"
            transport = entry.get("type")
            if transport not in {"stdio", "http", "sse", "streamable-http"}:
                transport = "stdio" if isinstance(entry.get("command"), str) else "http" if any(
                    isinstance(entry.get(key), str) for key in ("url", "serverUrl")) else "unknown"
            disabled = entry.get("disabled") is True or entry.get("enabled") is False
            record = {"id": _hash([installation, str(source.path.resolve()), name]), "name": safe_name,
                      "scope": source.scope, "transport": transport, "disabled": disabled}
            records.append(record)
    return records
